from dataclasses import dataclass
from typing import Optional, List
import aiohttp
from bs4 import BeautifulSoup
import json
import re
import logging

logger = logging.getLogger(__name__)

@dataclass
class CarInfo:
    source: str
    brand: str
    model: str
    year: Optional[int]
    price: int
    currency: str
    mileage: Optional[int]
    location: Optional[str]
    vin: Optional[str]
    photos: List[str]
    description: Optional[str]
    phone: Optional[str]
    seller_name: Optional[str]
    phone_hidden: bool = False

class ParseError(Exception):
    pass

class AutoRiaParser:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6",
        }

    async def parse(self, url: str) -> CarInfo:
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=self.timeout) as response:
                    if response.status != 200:
                        logger.warning("AutoRia parse failed: status=%s url=%s", response.status, url)
                        raise ParseError(f"Сайт недоступен, статус: {response.status}")
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, "lxml")

                    def _text(sel: str) -> Optional[str]:
                        el = soup.select_one(sel)
                        return el.get_text(" ", strip=True) if el else None

                    json_ld_script = soup.find("script", {"type": "application/ld+json"})
                    json_ld = {}
                    if json_ld_script and json_ld_script.string:
                        try:
                            json_ld = json.loads(json_ld_script.string)
                        except json.JSONDecodeError:
                            json_ld = {}

                    # Title / basic info
                    title = _text("#basicInfoTitle h1") or _text("h1") or ""
                    title_norm = re.sub(r"\s+", " ", title.replace("\u00a0", " ").replace("\u202f", " ")).strip()
                    brand = json_ld.get("brand", {}).get("name") or ""
                    model = json_ld.get("model") or ""
                    year = int(json_ld.get("vehicleModelDate")) if json_ld.get("vehicleModelDate") else None

                    if title_norm:
                        year_match = re.search(r"(19\d{2}|20\d{2})", title_norm)
                        if year is None and year_match:
                            year = int(year_match.group(0))
                        if not brand or not model:
                            parts = title_norm.split()
                            if not brand and parts:
                                brand = parts[0]
                            if not model and len(parts) > 1:
                                model = " ".join([p for p in parts[1:] if not re.fullmatch(r"(19\d{2}|20\d{2})", p)])

                    # Price
                    price_text = _text("#basicInfoPrice") or _text("#sidePrice") or _text("#basicInfoPriceRow") or ""
                    def _extract_price(text: str) -> tuple[int, str]:
                        text = re.sub(r"\s+", " ", text.replace("\u00a0", " ").replace("\u202f", " "))
                        usd = re.search(r"([0-9][0-9\s]*)\s*\$", text)
                        eur = re.search(r"([0-9][0-9\s]*)\s*€", text)
                        uah = re.search(r"([0-9][0-9\s]*)\s*грн", text)
                        if usd:
                            return int(re.sub(r"\s", "", usd.group(1))), "USD"
                        if eur:
                            return int(re.sub(r"\s", "", eur.group(1))), "EUR"
                        if uah:
                            return int(re.sub(r"\s", "", uah.group(1))), "UAH"
                        any_num = re.search(r"([0-9][0-9\s]*)", text)
                        if any_num:
                            return int(re.sub(r"\s", "", any_num.group(1))), "USD"
                        return 0, "USD"
                    price, currency = _extract_price(price_text)

                    # Mileage
                    mileage = None
                    mileage_text = _text("#basicInfoTableMainInfo") or ""
                    mileage_match = re.search(r"(\d+[\s\u00a0\u202f]*\d*)\s*тис\.?\s*км", mileage_text)
                    if mileage_match:
                        mileage = int(float(mileage_match.group(1).replace(" ", "").replace("\u00a0", "").replace("\u202f", "").replace(",", ".")) * 1000)

                    # Location
                    location = _text("#basicInfoTableMainInfoGeo span") or _text("#basicInfoTableMainInfoGeo") or _text("li.item._region") or _text("span.region")

                    # Description
                    description = (
                        _text(".expandable-text-template-text span")
                        or _text(".expandable-text-template-text")
                        or _text("div.description")
                        or _text("div.auto-description_text")
                    )

                    # Photos
                    photos: List[str] = []
                    for img in soup.select("#photoSlider img[data-src], #photoSlider img[src], .photo-slider img[data-src], .photo-slider img[src], picture source[data-src], picture img[data-src], picture img[src]"):
                        src = img.get("data-src") or img.get("src")
                        if not src:
                            continue
                        if src.startswith("//"):
                            src = "https:" + src
                        if src not in photos:
                            photos.append(src)
                        if len(photos) >= 5:
                            break

                    # Seller name
                    seller_name = _text("#sellerInfoUserName") or _text("div.seller_info_name") or _text("h4.seller_name")

                    # Phone (AutoRia often скрывает номер; пробуем API)
                    phone = None
                    phone_el = soup.select_one("#sellerInfo a[href^='tel:']") or soup.select_one("a[href^='tel:']")
                    if phone_el and phone_el.get("href"):
                        phone = phone_el.get("href", "").replace("tel:", "").strip()
                    if not phone and phone_el:
                        phone = phone_el.get_text(strip=True)
                    if not phone:
                        phone_data = await self._fetch_phone_data(session, html, url)
                        phone = phone_data[0]
                        if not seller_name and phone_data[1]:
                            seller_name = phone_data[1]
                    phone_hidden = phone is None

                    # VIN
                    vin = None
                    vin_text = _text("#badgesVin span") or _text("#badgesVervin span") or _text("#badgesVin") or _text("#badgesVervin")
                    vin_match = re.search(r"[A-HJ-NPR-Z0-9]{17}", vin_text or "")
                    if vin_match:
                        vin = vin_match.group(0)
                    else:
                        vin_match = re.search(r"[A-HJ-NPR-Z0-9]{17}", html)
                        vin = vin_match.group(0) if vin_match else None

                    return CarInfo(
                        source="auto_ria",
                        brand=brand or "Unknown",
                        model=model or "Unknown",
                        year=year,
                        price=price,
                        currency=currency,
                        mileage=mileage,
                        location=location,
                        vin=vin,
                        photos=photos,
                        description=description,
                        phone=phone,
                        seller_name=seller_name,
                        phone_hidden=phone_hidden
                    )

        except aiohttp.ClientError as e:
            logger.exception("AutoRia parse network error url=%s", url)
            raise ParseError(f"Ошибка сети: {e}")
        except Exception as e:
            logger.exception("AutoRia parse error url=%s", url)
            raise ParseError(f"Не удалось распознать объявление: {e}")

    async def _fetch_phone_data(
        self,
        session: aiohttp.ClientSession,
        html: str,
        url: str,
    ) -> tuple[Optional[str], Optional[str]]:
        auto_id = None
        m = re.search(r"_(\d+)\.html", url)
        if m:
            auto_id = m.group(1)

        phone_url = None
        # Try to find explicit phone url in html
        url_match = re.search(r"(https?://[^\"\\s]+phone[^\"\\s]+)", html)
        if url_match:
            phone_url = url_match.group(1)
        if not phone_url:
            data_url = re.search(r"phoneUrl\\s*[:=]\\s*[\"']([^\"']+)[\"']", html)
            if data_url:
                phone_url = data_url.group(1)

        hash_value = None
        for pattern in [r"phone_hash\\s*[:=]\\s*[\"']([^\"']+)[\"']", r"hash\\s*[:=]\\s*[\"']([^\"']+)[\"']"]:
            hm = re.search(pattern, html)
            if hm:
                hash_value = hm.group(1)
                break

        # Try AutoRia BFF popup endpoint (2-step flow)
        user_id = None
        phone_id = None
        title = None
        m_user = re.search(r'"userId"\s*:\s*"?(\d+)"?', html)
        if m_user:
            user_id = m_user.group(1)
        m_phone = re.search(r'"phoneId"\s*:\s*"?(\d+)"?', html)
        if m_phone:
            phone_id = m_phone.group(1)
        m_title = re.search(r'"title"\s*:\s*"([^"]+)"', html)
        if m_title:
            title = m_title.group(1)
        if auto_id and user_id and phone_id:
            payload = {
                "autoId": int(auto_id),
                "blockId": "autoPhone",
                "popUpId": "autoPhone",
                "device": "desktop-web",
                "langId": 4,
                "isLoginRequired": False,
                "isConfirmPhoneEmailRequired": False,
                "formId": None,
                "data": [
                    ["userId", str(user_id)],
                    ["phoneId", str(phone_id)],
                    ["title", title or ""],
                    ["isCheckedVin", ""],
                ],
                "params": {
                    "userId": str(user_id),
                    "phoneId": str(phone_id),
                    "title": title or "",
                    "isCheckedVin": "",
                },
            }
            try:
                req_headers = dict(session.headers)
                req_headers.update(
                    {
                        "x-ria-source": "vue3-1.56.0",
                        "origin": "https://auto.ria.com",
                        "referer": url,
                    }
                )
                async with session.post(
                    "https://auto.ria.com/bff/final-page/public/auto/popUp/",
                    json=payload,
                    timeout=self.timeout,
                    headers=req_headers,
                ) as resp:
                    if resp.status == 200:
                        raw_text = await resp.text()
                        m_raw_phone = re.search(r"\"phoneStr\"\s*:\s*\"([^\"]+)\"", raw_text)
                        if m_raw_phone:
                            return m_raw_phone.group(1).replace("tel:", "").strip(), None
                        m_raw_tel = re.search(r"tel:[0-9\s\-()]+", raw_text)
                        if m_raw_tel:
                            return m_raw_tel.group(0).replace("tel:", "").strip(), None
                        try:
                            data = json.loads(raw_text)
                        except Exception:
                            data = None
                        if not data:
                            return None, None
                        phone = None
                        seller = None
                        phone = None
                        if isinstance(data, dict):
                            phone = data.get("additionalParams", {}).get("phoneStr")
                        if not phone:
                            phone = self._deep_find_phone_str(data)
                        if not phone and isinstance(data, dict):
                            for tmpl in data.get("templates", []) or []:
                                if tmpl.get("id") == "autoPhoneCall":
                                    phone = tmpl.get("link") or phone
                                    for el in tmpl.get("elements", []) or []:
                                        if el.get("content"):
                                            phone = el.get("content")
                                            break
                                if tmpl.get("id") == "autoPhoneMainInfoRow":
                                    for sub in tmpl.get("templates", []) or []:
                                        if sub.get("id") == "autoPhoneMainInfoColB":
                                            for sub2 in sub.get("templates", []) or []:
                                                if sub2.get("id") == "autoPhoneMainInfoName":
                                                    for el in sub2.get("elements", []) or []:
                                                        if el.get("content"):
                                                            seller = el.get("content")
                                                            break
                        if phone:
                            phone = str(phone).replace("tel:", "").strip()
                        data_str = json.dumps(data, ensure_ascii=False)
                        if not phone:
                            phone_match = re.search(r"(\+?\d[\d\s\-()]{7,}\d)", data_str)
                            if phone_match:
                                phone = phone_match.group(1).strip()
                        if not phone:
                            m_phone_str = re.search(r"\"phoneStr\":\"([^\"]+)\"", data_str)
                            if m_phone_str:
                                phone = m_phone_str.group(1).replace("tel:", "").strip()
                        if not phone:
                            phone = self._deep_find_phone(data)
                        return phone, seller
            except Exception:
                pass
        elif auto_id:
            # Fallback attempt with minimal payload
            payload = {
                "autoId": int(auto_id),
                "blockId": "autoPhone",
                "popUpId": "autoPhone",
                "device": "desktop-web",
                "langId": 4,
                "isLoginRequired": False,
                "isConfirmPhoneEmailRequired": False,
                "formId": None,
                "data": [],
                "params": {},
            }
            try:
                req_headers = dict(session.headers)
                req_headers.update(
                    {
                        "x-ria-source": "vue3-1.56.0",
                        "origin": "https://auto.ria.com",
                        "referer": url,
                    }
                )
                async with session.post(
                    "https://auto.ria.com/bff/final-page/public/auto/popUp/",
                    json=payload,
                    timeout=self.timeout,
                    headers=req_headers,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        phone = self._deep_find_phone(data)
                        if phone:
                            return phone, None
            except Exception:
                pass

        candidate_urls = []
        if phone_url:
            candidate_urls.append(phone_url)
        if auto_id and hash_value:
            candidate_urls.extend(
                [
                    f"https://auto.ria.com/auto_used/phone/?auto_id={auto_id}&hash={hash_value}",
                    f"https://auto.ria.com/blocks/auto/phone/{auto_id}?hash={hash_value}",
                ]
            )

        for candidate in candidate_urls:
            try:
                async with session.get(candidate, timeout=self.timeout) as resp:
                    if resp.status != 200:
                        continue
                    content_type = resp.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        data = await resp.json()
                        for key in ("phone", "phones", "phoneNumber"):
                            if key in data:
                                value = data[key]
                                if isinstance(value, list) and value:
                                    return str(value[0]).strip(), None
                                if isinstance(value, str):
                                    return value.strip(), None
                    text = await resp.text()
                    phone_match = re.search(r"(\+?\d[\d\s\-()]{7,}\d)", text)
                    if phone_match:
                        return phone_match.group(1).strip(), None
            except Exception:
                continue
        return None, None

    def _deep_find_phone(self, data) -> Optional[str]:
        def walk(obj):
            if isinstance(obj, str):
                return obj
            if isinstance(obj, dict):
                for v in obj.values():
                    res = walk(v)
                    if res:
                        return res
            if isinstance(obj, list):
                for v in obj:
                    res = walk(v)
                    if res:
                        return res
            return None

        candidate = None
        stack = [data]
        phone_re = re.compile(r"(\+?\d[\d\s\-()]{7,}\d)")
        while stack:
            obj = stack.pop()
            if isinstance(obj, str):
                m = phone_re.search(obj)
                if m:
                    candidate = m.group(1).strip()
                    break
            elif isinstance(obj, dict):
                for v in obj.values():
                    stack.append(v)
            elif isinstance(obj, list):
                for v in obj:
                    stack.append(v)
        return candidate

    def _deep_find_phone_str(self, data) -> Optional[str]:
        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "phoneStr" and isinstance(v, str):
                        return v
                    if k == "link" and isinstance(v, str) and v.startswith("tel:"):
                        return v
                    res = walk(v)
                    if res:
                        return res
            elif isinstance(obj, list):
                for v in obj:
                    res = walk(v)
                    if res:
                        return res
            return None

        result = walk(data)
        if result:
            return str(result).replace("tel:", "").strip()
        return None


class OlxParser:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6",
        }

    async def _fetch_phone(self, session: aiohttp.ClientSession, html: str, url: str) -> Optional[str]:
        ad_id = None
        m_ad = re.search(r"ad-id=(\d+)", html)
        if m_ad:
            ad_id = m_ad.group(1)
        if not ad_id:
            m_id = re.search(r"ID:\s*(\d+)", html)
            if m_id:
                ad_id = m_id.group(1)
        if not ad_id:
            return None

        phone_url = f"https://www.olx.ua/api/v1/offers/{ad_id}/phones/"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": url,
            "X-Platform": "desktop",
        }
        headers.update(self.headers)
        try:
            async with session.get(phone_url, headers=headers, timeout=self.timeout) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        except Exception:
            return None

        phones = None
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], dict):
                phones = data["data"].get("phones")
            if phones is None:
                phones = data.get("phones")
        if isinstance(phones, list) and phones:
            return str(phones[0]).strip()
        return None

    async def parse(self, url: str) -> CarInfo:
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=self.timeout) as response:
                    if response.status != 200:
                        logger.warning("OLX parse failed: status=%s url=%s", response.status, url)
                        raise ParseError(f"Сайт недоступен, статус: {response.status}")

                    html = await response.text()
                    soup = BeautifulSoup(html, "lxml")

                    def meta_content(name: str, attr: str = "property") -> Optional[str]:
                        tag = soup.find("meta", {attr: name})
                        return tag["content"].strip() if tag and tag.get("content") else None

                    def _text(sel: str) -> Optional[str]:
                        el = soup.select_one(sel)
                        return el.get_text(" ", strip=True) if el else None

                    title = (
                        _text("[data-testid='offer_title'] h4")
                        or _text("h1")
                        or meta_content("og:title")
                        or ""
                    )
                    title_norm = re.sub(r"\s+", " ", title.replace("\u00a0", " ").replace("\u202f", " ")).strip()
                    description = (
                        _text("[data-testid='ad_description'] .css-19duwlz")
                        or _text("[data-testid='ad_description']")
                        or meta_content("og:description")
                    )
                    if description and description.lower().startswith("опис"):
                        description = description[4:].strip()

                    price_text = _text("[data-testid='ad-price-container'] h3") or meta_content("product:price:amount") or meta_content("og:price:amount") or ""
                    currency = meta_content("product:price:currency") or ("USD" if "$" in price_text else "UAH" if "грн" in price_text else "EUR" if "€" in price_text else "USD")
                    price = int(re.sub(r"\D", "", price_text)) if price_text else 0

                    year = None
                    year_match = re.search(r"(19\d{2}|20\d{2})", title_norm)
                    if year_match:
                        year = int(year_match.group(0))

                    brand = ""
                    model = ""
                    model_from_params = None
                    mod_from_params = None
                    brand_from_params = None
                    if title_norm:
                        parts = title_norm.split()
                        blacklist = {
                            "продам",
                            "продаю",
                            "срочно",
                            "терміново",
                            "терминово",
                            "свій",
                            "своя",
                            "свое",
                            "офіційний",
                            "офіційна",
                            "офіційне",
                            "официальный",
                            "официальная",
                            "официальное",
                        }
                        idx = 0
                        while idx < len(parts) and parts[idx].lower().strip("-.,") in blacklist:
                            idx += 1
                        brand = parts[idx] if idx < len(parts) else ""
                        if brand:
                            model = " ".join(parts[idx + 1:])
                        if year:
                            model = model.replace(str(year), "").strip()
                        model = re.sub(r"\b(19\d{2}|20\d{2})\b", "", model).strip()
                        model = re.sub(r"\bг\.?\b", "", model, flags=re.IGNORECASE).strip()
                        model = re.sub(r"\s+", " ", model).strip()

                    location = (
                        meta_content("og:locality")
                        or meta_content("og:region")
                        or _text("[data-testid='ad-location']")
                    )

                    photos: List[str] = []
                    for img in soup.select("[data-testid='ad-photo'] img, [data-testid='swiper-image'], [data-testid='swiper-image-lazy']"):
                        src = img.get("src")
                        if not src:
                            continue
                        if src.startswith("//"):
                            src = "https:" + src
                        if src not in photos:
                            photos.append(src)
                        if len(photos) >= 5:
                            break
                    if not photos:
                        og_image = meta_content("og:image")
                        if og_image:
                            photos.append(og_image)

                    vin = None
                    mileage = None
                    params = soup.select("[data-testid='ad-parameters-container'] p")
                    for p in params:
                        text = p.get_text(" ", strip=True)
                        if ":" in text:
                            key, val = [t.strip() for t in text.split(":", 1)]
                            key_l = key.lower()
                            if key_l == "модель":
                                model_from_params = val
                            elif key_l in {"модифікація", "модификация"}:
                                mod_from_params = val
                            elif key_l in {"марка", "бренд"}:
                                brand_from_params = val
                        if "VIN" in text.upper():
                            vin_match = re.search(r"[A-HJ-NPR-Z0-9]{17}", text.upper())
                            if vin_match:
                                vin = vin_match.group(0)
                        if "Пробіг" in text or "Пробег" in text:
                            m = re.search(r"(\d+[\s\u00a0]*\d*)\s*тис", text)
                            if m:
                                mileage = int(float(m.group(1).replace(" ", "").replace("\u00a0", "").replace(",", ".")) * 1000)

                    if brand_from_params:
                        brand = brand_from_params
                    if model_from_params:
                        model = model_from_params
                    if mod_from_params:
                        model = f"{model} {mod_from_params}".strip()

                    if model_from_params and brand and brand.lower() == model_from_params.lower():
                        brand = ""
                        parts = title_norm.split() if title_norm else []
                        target = model_from_params.lower()
                        for i, part in enumerate(parts):
                            if part.lower().strip("-.,") == target:
                                for j in range(i - 1, -1, -1):
                                    cand = parts[j].lower().strip("-.,")
                                    if cand in blacklist:
                                        continue
                                    if re.fullmatch(r"(19\d{2}|20\d{2})", cand):
                                        continue
                                    brand = parts[j]
                                    break
                                break

                    phone = None
                    phone_el = soup.select_one("a[data-testid='contact-phone'][href^='tel:']") or soup.select_one("a[href^='tel:']")
                    if phone_el and phone_el.get("href"):
                        phone = phone_el.get("href", "").replace("tel:", "").strip()
                    if not phone and phone_el:
                        phone = phone_el.get_text(strip=True)
                    if not phone:
                        phone = await self._fetch_phone(session, html, url)

                    return CarInfo(
                        source="olx",
                        brand=brand or "Unknown",
                        model=model or "Unknown",
                        year=year,
                        price=price,
                        currency=currency,
                        mileage=mileage,
                        location=location,
                        vin=vin,
                        photos=photos,
                        description=description,
                        phone=phone,
                        seller_name=None,
                        phone_hidden=phone is None,
                    )
        except aiohttp.ClientError as e:
            logger.exception("OLX parse network error url=%s", url)
            raise ParseError(f"Ошибка сети: {e}")
        except Exception as e:
            logger.exception("OLX parse error url=%s", url)
            raise ParseError(f"Не удалось распознать объявление: {e}")


async def parse_auto_ria(url: str) -> CarInfo:
    parser = AutoRiaParser()
    return await parser.parse(url)


async def parse_olx(url: str) -> CarInfo:
    parser = OlxParser()
    return await parser.parse(url)
