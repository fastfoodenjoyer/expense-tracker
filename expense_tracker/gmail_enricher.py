"""Gmail integration for Ozon order enrichment."""

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import quopri
import email
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

    def _get_html_from_eml(self, eml_bytes: bytes) -> str:
        """Parse EML and extract HTML part."""
        try:
            msg = email.message_from_bytes(eml_bytes)
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode("utf-8", errors="ignore")
        except Exception:
            pass
        return ""

    def _extract_items(self, html: str) -> List[str]:
        """Extract item names from Ozon order email HTML."""
        # 1. Product links usually have names as text
        links = re.findall(r'<a[^>]*?href=\"https?://(?:www\.)?ozon\.ru/product/[^>]*?>\s*([^<]{10,250})\s*</a>', html, re.S)
        names = [re.sub(r'\s+', ' ', n).strip() for n in links]
        
        # 2. Spans with typical item styling
        if not names:
            spans = re.findall(r'<span[^>]*?>\s*([^<]{15,250})\s*</span>', html, re.S)
            for s in spans:
                clean = re.sub(r'\s+', ' ', s).strip()
                # Ozon item names are usually descriptive and don't contain these words
                # Filter out addresses, service messages, etc.
                if len(clean) > 15 and not any(x in clean.lower() for x in [
                    'итого', 'скидка', 'стоимость', 'баллы', 'здравствуйте', 'ozon', 
                    'чека', 'заказ', 'команда', 'озон', 'лимита', 'карту', 'счёте', 
                    'бесплатно', 'вашей', 'способом', 'платеж', 'на карту', 'пункте', 
                    'доставки', 'перейти', 'отследить', 'подробнее', 'подарок',
                    'улица', 'корпус', 'санкт-петербург', 'москва', 'дом', 'квартира'
                ]):
                    names.append(clean)
        
        return list(dict.fromkeys(names))

    def fetch_ozon_orders(self, limit: int = 5) -> Dict[str, str]:
        """[LEGACY] Fetch Ozon order details from Gmail.
        This approach is deprecated. Future implementation will use direct PDF processing.
        """
        service = self._get_service()
        if not service:
            return {}

        order_map = {}
        try:
            # Query for Ozon-related emails
            results = service.users().messages().list(userId="me", q="Subject:Ozon", maxResults=limit).execute()
            messages = results.get("messages", [])

            for msg_info in messages:
                m_id = msg_info["id"]
                msg_data = service.users().messages().get(userId="me", id=m_id).execute()
                
                # Walk through all parts to find EML attachments or HTML bodies
                def process_payload(payload):
                    if payload.get("mimeType") == "message/rfc822":
                        aid = payload.get("body", {}).get("attachmentId")
                        if aid:
                            att = service.users().messages().attachments().get(
                                userId="me", messageId=m_id, id=aid
                            ).execute()
                            eml_data = base64.urlsafe_b64decode(att["data"])
                            
                            # filename often contains status
                            filename = payload.get("filename", "")
                            
                            html = self._get_html_from_eml(eml_data)
                            if html:
                                order_match = re.search(r"(\d{8}-\d{4})", html)
                                if order_match:
                                    order_no = order_match.group(1)
                                    items = self._extract_items(html)
                                    
                                    if items:
                                        details = ", ".join(items[:3])
                                    else:
                                        # Use filename if it's informative
                                        details = filename.replace(".eml", "").strip() if filename else "Заказ Ozon"
                                        
                                    # Prioritize detailed names over generic ones
                                    if order_no not in order_map or len(details) > len(order_map[order_no]):
                                        order_map[order_no] = details
                    
                    if "parts" in payload:
                        for part in payload["parts"]:
                            process_payload(part)

                process_payload(msg_data["payload"])
                                
        except Exception as e:
            logger.error(f"Error fetching Ozon orders from Gmail: {e}")

        return order_map
