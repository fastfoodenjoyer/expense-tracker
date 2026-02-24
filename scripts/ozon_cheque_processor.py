"""Ozon cheque PDF parser and Google Sheets updater.

Standard procedure for processing Ozon cheques:
1. Parse PDF cheques (extract order number, date, items, prices)
2. Update "Ozon Заказы" sheet: 1 row = 1 item (deduplicated)
3. Update "Транзакции" sheet: enrich descriptions with item names

Usage:
    from scripts.ozon_cheque_processor import process_ozon_cheques
    process_ozon_cheques("/path/to/cheques/", sheet_id="...", credentials_path="...")
"""

import json
import os
import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# Items to exclude from the order (fees, delivery, processing)
SKIP_KEYWORDS = ['Доставка', 'Обработка заказа', 'Курьерская доставка']


def parse_cheque_pdf(pdf_path: str) -> dict:
    """Parse a single Ozon cheque PDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Dict with keys: file, order, cheque, date, time, total, items
    """
    import pdfplumber

    filename = os.path.basename(pdf_path)

    with pdfplumber.open(pdf_path) as pdf:
        text = ''
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + '\n'

    cheque_num = re.search(r'Кассовый чек № (\d+)', text)
    date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})', text)
    total_match = re.search(r'ИТОГ\s+≡([\d\s,\.]+)', text)

    # Extract items between 'Приход' and 'ИТОГ'
    items_section = re.search(r'Приход\n(.*?)ИТОГ', text, re.DOTALL)
    items = []
    if items_section:
        lines = items_section.group(1).strip().split('\n')
        current_item = ''
        for line in lines:
            if re.match(r'^\d+\.', line):
                if current_item:
                    items.append(current_item)
                current_item = line
            else:
                current_item += ' ' + line
        if current_item:
            items.append(current_item)

    # Extract order number from filename
    order = re.search(r'ozon_cheque_(\d+-\d+)', filename)

    return {
        'file': filename,
        'order': order.group(1) if order else '',
        'cheque': cheque_num.group(1) if cheque_num else '',
        'date': date_match.group(1) if date_match else '',
        'time': date_match.group(2) if date_match else '',
        'total': total_match.group(1).strip() if total_match else '',
        'items': items,
    }


def parse_all_cheques(cheques_dir: str) -> List[dict]:
    """Parse all PDF cheques in a directory.

    Args:
        cheques_dir: Path to directory containing PDF files

    Returns:
        List of parsed cheque dicts
    """
    pdfs = sorted([f for f in os.listdir(cheques_dir) if f.endswith('.pdf')])
    logger.info(f"Found {len(pdfs)} PDF cheques in {cheques_dir}")

    results = []
    for pdf_file in pdfs:
        path = os.path.join(cheques_dir, pdf_file)
        try:
            result = parse_cheque_pdf(path)
            results.append(result)
            logger.debug(f"Parsed {pdf_file}: order={result['order']}, items={len(result['items'])}")
        except Exception as e:
            logger.error(f"Failed to parse {pdf_file}: {e}")

    return results


def _clean_item_name(item_raw: str) -> str:
    """Extract clean item name from raw cheque line."""
    name = re.sub(r'^\d+\.\s*', '', item_raw)
    name = re.sub(r'\d+\s*x\s*[\d,\.]+\s*≡[\d,\.]+.*', '', name).strip()
    return name


def _extract_item_price(item_raw: str) -> str:
    """Extract price from raw cheque line."""
    price_match = re.search(r'≡([\d\s,\.]+?)(?:\s|$)', item_raw)
    return price_match.group(1).strip() if price_match else ''


def _should_skip_item(name: str) -> bool:
    """Check if item should be excluded (delivery, processing fees)."""
    return any(skip in name for skip in SKIP_KEYWORDS) or not name


def build_item_rows(cheques: List[dict]) -> Tuple[List[list], Dict[str, List[str]]]:
    """Build per-item rows for "Ozon Заказы" and per-order item lists.

    Deduplicates items across duplicate cheques (order placement + delivery).

    Args:
        cheques: List of parsed cheque dicts

    Returns:
        Tuple of (item_rows, order_items) where:
            item_rows: List of [order_id, date, item_name, price, total]
            order_items: Dict mapping order_id -> list of item names
    """
    item_rows = []
    order_items: Dict[str, List[str]] = {}
    order_dates: Dict[str, str] = {}
    seen: set = set()

    for c in cheques:
        order_id = c['order']
        if order_id not in order_dates:
            order_dates[order_id] = f"{c['date']} {c['time']}"

        for item_raw in c['items']:
            name = _clean_item_name(item_raw)
            if _should_skip_item(name):
                continue

            price = _extract_item_price(item_raw)

            # Deduplicate by (order, item_name)
            dedup_key = (order_id, name)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            item_rows.append([order_id, order_dates[order_id], name, price, c['total']])

            if order_id not in order_items:
                order_items[order_id] = []
            order_items[order_id].append(name)

    item_rows.sort(key=lambda x: x[0])
    return item_rows, order_items


def update_google_sheets(
    item_rows: List[list],
    order_items: Dict[str, List[str]],
    sheet_id: str,
    credentials_path: str,
) -> Tuple[int, int]:
    """Update Google Sheets with parsed cheque data.

    1. Overwrites "Ozon Заказы" sheet (1 row = 1 item)
    2. Updates "Транзакции" descriptions for matching order numbers

    Args:
        item_rows: Per-item rows for "Ozon Заказы"
        order_items: Per-order item lists for "Транзакции" enrichment
        sheet_id: Google Sheets document ID
        credentials_path: Path to service account credentials JSON

    Returns:
        Tuple of (items_written, transactions_updated)
    """
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_file(
        credentials_path,
        scopes=[
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive',
        ],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)

    # --- Update "Ozon Заказы" ---
    try:
        ws_ozon = sh.worksheet('Ozon Заказы')
        ws_ozon.clear()
    except Exception:
        ws_ozon = sh.add_worksheet(title='Ozon Заказы', rows=200, cols=6)

    header = ['Номер заказа', 'Дата', 'Товар', 'Цена товара (₽)', 'Итого заказ (₽)']
    ws_ozon.update(values=[header] + item_rows, range_name=f'A1:E{len(item_rows) + 1}')
    logger.info(f"Ozon Заказы: wrote {len(item_rows)} item rows")

    # --- Update "Транзакции" descriptions ---
    transactions_updated = 0
    try:
        ws_trans = sh.worksheet('Транзакции')
        all_trans = ws_trans.get_all_values()
        header_trans = all_trans[0]
        desc_col = header_trans.index('Описание')

        for i, row in enumerate(all_trans[1:], 2):
            desc = row[desc_col] if desc_col < len(row) else ''
            match = re.search(r'заказ №\s*(\d+-\d+)', desc, re.IGNORECASE)
            if match:
                order_id = match.group(1)
                if order_id in order_items:
                    items_str = ', '.join(order_items[order_id])
                    new_desc = f'Заказ №{order_id}, товары: {items_str}'
                    ws_trans.update_cell(i, desc_col + 1, new_desc)
                    transactions_updated += 1
                    logger.info(f"Транзакция row {i}: {new_desc[:80]}...")

    except Exception as e:
        logger.warning(f"Could not update Транзакции: {e}")

    logger.info(f"Транзакции: updated {transactions_updated} descriptions")
    return len(item_rows), transactions_updated


def process_ozon_cheques(
    cheques_dir: str,
    sheet_id: str = '1h5VlyXEcoBhjNHMOfWHTxEbV8EHyAdfdb97IQ1bDR5U',
    credentials_path: str = os.path.expanduser('~/.expense-tracker/credentials.json'),
    cache_path: str = '/tmp/ozon_cheques_parsed.json',
) -> dict:
    """Full pipeline: parse cheque PDFs and update Google Sheets.

    Args:
        cheques_dir: Directory containing Ozon cheque PDFs
        sheet_id: Google Sheets document ID
        credentials_path: Path to service account credentials
        cache_path: Path to save parsed cheques JSON cache

    Returns:
        Summary dict with counts
    """
    # Parse
    cheques = parse_all_cheques(cheques_dir)

    # Cache
    if cache_path:
        with open(cache_path, 'w') as f:
            json.dump(cheques, f, ensure_ascii=False, indent=2)
        logger.debug(f"Cached parsed cheques to {cache_path}")

    # Build rows
    item_rows, order_items = build_item_rows(cheques)

    # Update sheets
    items_written, transactions_updated = update_google_sheets(
        item_rows, order_items, sheet_id, credentials_path
    )

    return {
        'cheques_parsed': len(cheques),
        'unique_orders': len(order_items),
        'items_written': items_written,
        'transactions_updated': transactions_updated,
    }


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    if len(sys.argv) < 2:
        print("Usage: python ozon_cheque_processor.py <cheques_directory>")
        sys.exit(1)

    result = process_ozon_cheques(sys.argv[1])
    print(f"\nSummary:")
    print(f"  Cheques parsed: {result['cheques_parsed']}")
    print(f"  Unique orders: {result['unique_orders']}")
    print(f"  Items written to sheet: {result['items_written']}")
    print(f"  Transactions updated: {result['transactions_updated']}")
