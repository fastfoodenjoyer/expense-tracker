"""Gmail integration for Ozon order enrichment."""

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import quopri
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# Scopes required for reading Gmail
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

class GmailEnricher:
    """Enriches transactions by fetching order details from Gmail."""

    def __init__(self, token_path: str = "~/.expense-tracker/gmail_token.json"):
        """Initialize with token path."""
        self.token_path = Path(token_path).expanduser()
        self._service = None

    def _get_service(self):
        """Get or initialize Gmail service."""
        if self._service:
            return self._service

        if not self.token_path.exists():
            logger.warning(f"Gmail token not found at {self.token_path}")
            return None

        try:
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            
            self._service = build("gmail", "v1", credentials=creds)
            return self._service
        except Exception as e:
            logger.error(f"Failed to initialize Gmail service: {e}")
            return None

    def _get_html_content(self, payload, service, msg_id) -> List[str]:
        """Recursively extract all HTML parts from a message payload, including attachments."""
        htmls = []
        mime_type = payload.get("mimeType")

        # Case 1: text/html part
        if mime_type == "text/html":
            data = payload.get("body", {}).get("data")
            if data:
                htmls.append(base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore"))

        # Case 2: message/rfc822 attachment (the forwarded emails)
        if mime_type == "message/rfc822":
            aid = payload.get("body", {}).get("attachmentId")
            if aid and service:
                try:
                    att = service.users().messages().attachments().get(
                        userId="me", messageId=msg_id, id=aid
                    ).execute()
                    data = att.get("data")
                    if data:
                        raw = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                        # Decode Quoted-Printable if it looks like it
                        if "=3D" in raw or "=\r\n" in raw:
                            try:
                                raw = quopri.decodestring(raw.encode("ascii", errors="ignore")).decode("utf-8", errors="ignore")
                            except Exception:
                                pass
                        htmls.append(raw)
                except Exception as e:
                    logger.debug(f"Could not fetch attachment: {e}")

        # Recurse into parts
        if "parts" in payload:
            for part in payload["parts"]:
                htmls.extend(self._get_html_content(part, service, msg_id))

        return htmls

    def _extract_items_from_html(self, html: str) -> List[str]:
        """Extract item names from Ozon order email HTML."""
        # Find item names followed by prices with RUB symbol or '=' (encoded)
        # Ozon emails are complex, so we use a loose but filtered match
        # items = re.findall(r">([^<]{10,200})<.*?(\d+[\s\d]*[.,]\d{2})\s*[₽=]", html, re.S)
        
        # New approach: search for the receipt link first to identify order detail blocks
        # but since we process HTML parts individually, let's look for order number
        order_match = re.search(r"(\d{8}-\d{4})", html)
        if not order_match:
            return []
            
        # Subject extraction as fallback
        subj_match = re.search(r"Subject:\s*=\?UTF-8\?Q\?([^\?]+)\?", html)
        if subj_match:
            try:
                subj = quopri.decodestring(subj_match.group(1).replace("_", " ")).decode("utf-8", errors="ignore")
                return [subj]
            except:
                pass
        
        # If we can't find item list, return a generic descriptive label
        if "Вернули деньги" in html:
            return ["Возврат средств"]
        if "Заказ принят" in html:
            return ["Новый заказ"]
        if "Ваш чек" in html:
            return ["Электронный чек"]
            
        return []

    def fetch_ozon_orders(self, limit: int = 20) -> Dict[str, str]:
        """Fetch recent Ozon order details from Gmail."""
        service = self._get_service()
        if not service:
            return {}

        order_map = {}
        try:
            # Search for Ozon emails
            query = 'Subject:Ozon'
            results = service.users().messages().list(userId="me", q=query, maxResults=limit).execute()
            messages = results.get("messages", [])

            for msg_info in messages:
                m_id = msg_info["id"]
                msg = service.users().messages().get(userId="me", id=m_id).execute()
                htmls = self._get_html_content(msg["payload"], service, m_id)
                
                for html in htmls:
                    # Find order numbers in HTML
                    orders = re.findall(r"(\d{8}-\d{4})", html)
                    if not orders:
                        continue
                        
                    items = self._extract_items_from_html(html)
                    if items:
                        details = ", ".join(items[:3])
                        for order_no in set(orders):
                            if order_no not in order_map or "чек" in details.lower():
                                order_map[order_no] = details
                                
        except Exception as e:
            logger.error(f"Error fetching Ozon orders from Gmail: {e}")

        return order_map
