from app.crm.models import Lead, CallLog
from .parser import CarInfo
from app.db import engine
from sqlalchemy import select, desc, asc, or_, and_
import re
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.crm.constants import CLOSED_STATUSES, ALLOWED_STATUSES

async def get_lead_by_source_url(url: str) -> Optional[Lead]:
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Lead).where(Lead.source_url == url))
        return result.scalars().first()


async def create_lead(car_info: CarInfo, url: str, manager_id: int) -> tuple[Lead, bool]:
    async with AsyncSession(engine) as session:
        existing = await session.execute(select(Lead).where(Lead.source_url == url))
        lead_existing = existing.scalars().first()
        if lead_existing:
            return lead_existing, False
        def _trim(value: Optional[str], limit: int) -> Optional[str]:
            if value is None:
                return None
            value = value.strip()
            return value[:limit]
        new_lead = Lead(
            manager_id=manager_id,
            source=car_info.source,
            source_url=url,
            status="new",
            car_brand=car_info.brand,
            car_model=car_info.model,
            car_year=car_info.year,
            car_price=car_info.price,
            car_price_currency=car_info.currency,
            car_mileage=car_info.mileage,
            car_location=car_info.location,
            car_vin=car_info.vin,
            car_photos=car_info.photos,
            car_description=car_info.description,
            owner_name=car_info.seller_name,
            owner_phone=car_info.phone,
            owner_phone_hidden=car_info.phone_hidden,
        )
        new_lead.car_brand = _trim(new_lead.car_brand, 50) or "Unknown"
        new_lead.car_model = _trim(new_lead.car_model, 50) or "Unknown"
        new_lead.car_price_currency = _trim(new_lead.car_price_currency, 3) or "USD"
        new_lead.car_location = _trim(new_lead.car_location, 100)
        new_lead.car_vin = _trim(new_lead.car_vin, 20)
        new_lead.owner_name = _trim(new_lead.owner_name, 100)
        new_lead.owner_phone = _trim(new_lead.owner_phone, 20)
        session.add(new_lead)
        await session.commit()
        await session.refresh(new_lead)
        return new_lead, True

def _order_by_sort(sort_by: str):
    if sort_by == "price":
        return [Lead.car_price.asc().nulls_last()]
    if sort_by == "year":
        return [Lead.car_year.desc().nulls_last()]
    return [Lead.car_brand.asc().nulls_last(), Lead.car_model.asc().nulls_last()]


async def get_leads_for_pipeline(page: int = 0, page_size: int = 10, sort_by: str = "brand") -> List[Lead]:
    async with AsyncSession(engine) as session:
        stmt = (
            select(Lead)
            .where(Lead.status == "new")
            .order_by(*_order_by_sort(sort_by))
            .offset(page * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

async def get_lead_by_id(lead_id: int) -> Optional[Lead]:
    async with AsyncSession(engine) as session:
        return await session.get(Lead, lead_id)

async def get_first_lead_from_pipeline(sort_by: str = "brand") -> Optional[Lead]:
    leads = await get_leads_for_pipeline(page=0, page_size=1, sort_by=sort_by)
    return leads[0] if leads else None


async def get_leads_for_sale(page: int = 0, page_size: int = 10, sort_by: str = "brand") -> List[Lead]:
    async with AsyncSession(engine) as session:
        stmt = (
            select(Lead)
            .where(Lead.status.in_(["for_sale_set", "published"]))
            .order_by(*_order_by_sort(sort_by))
            .offset(page * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        return result.scalars().all()


async def get_leads_for_no_answer(page: int = 0, page_size: int = 10, sort_by: str = "brand") -> List[Lead]:
    async with AsyncSession(engine) as session:
        stmt = (
            select(Lead)
            .where(Lead.status == "no_answer")
            .order_by(*_order_by_sort(sort_by))
            .offset(page * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        return result.scalars().all()


def _extract_search_terms(query: str) -> tuple[list[str], list[int], list[int]]:
    text = query.strip().lower()
    numbers = [int(x) for x in re.findall(r"\d{2,6}", text)]
    words = re.findall(r"[a-zа-яёіїє0-9]+", text)
    years: list[int] = []
    prices: list[int] = []
    for num in numbers:
        if 1900 <= num <= 2100:
            years.append(num)
        elif num >= 1000:
            prices.append(num)
    tokens = [w for w in words if not w.isdigit()]
    return tokens, years, prices


async def search_sales(
    query: str,
    limit: int = 20,
    price_tolerance: int = 3000,
    year_tolerance: int = 1,
) -> List[Lead]:
    tokens, years, prices = _extract_search_terms(query)
    async with AsyncSession(engine) as session:
        conditions = [Lead.status.in_(["for_sale_set", "published"])]

        if tokens:
            token_clauses = []
            for t in tokens:
                like = f"%{t}%"
                token_clauses.append(Lead.car_brand.ilike(like))
                token_clauses.append(Lead.car_model.ilike(like))
                token_clauses.append(Lead.car_location.ilike(like))
                token_clauses.append(Lead.owner_name.ilike(like))
                token_clauses.append(Lead.owner_phone.ilike(like))
            conditions.append(or_(*token_clauses))

        if years:
            year = years[0]
            conditions.append(Lead.car_year.between(year - year_tolerance, year + year_tolerance))

        if prices:
            price = prices[0]
            conditions.append(Lead.car_price.between(price - price_tolerance, price + price_tolerance))

        stmt = (
            select(Lead)
            .where(and_(*conditions))
            .order_by(desc(Lead.updated_at), desc(Lead.created_at))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()


async def update_status(lead_id: int, status: str) -> Optional[Lead]:
    if status not in ALLOWED_STATUSES:
        return None
    async with AsyncSession(engine) as session:
        lead = await session.get(Lead, lead_id)
        if not lead:
            return None
        lead.status = status
        if status in CLOSED_STATUSES:
            lead.archived = True
        await session.commit()
        await session.refresh(lead)
        return lead


async def update_lead_fields(lead_id: int, **fields) -> Optional[Lead]:
    async with AsyncSession(engine) as session:
        lead = await session.get(Lead, lead_id)
        if not lead:
            return None
        for key, value in fields.items():
            if hasattr(lead, key):
                setattr(lead, key, value)
        await session.commit()
        await session.refresh(lead)
        return lead


async def update_priority(lead_id: int, priority: int) -> Optional[Lead]:
    if priority < 1 or priority > 5:
        return None
    async with AsyncSession(engine) as session:
        lead = await session.get(Lead, lead_id)
        if not lead:
            return None
        lead.priority = priority
        await session.commit()
        await session.refresh(lead)
        return lead


async def add_call_log(
    lead_id: int,
    manager_id: int,
    result: str,
    notes: str | None = None,
    next_action_type: str | None = None,
    next_action_date=None,
) -> CallLog:
    async with AsyncSession(engine) as session:
        log = CallLog(
            lead_id=lead_id,
            manager_id=manager_id,
            result=result,
            notes=notes,
            next_action_type=next_action_type,
            next_action_date=next_action_date,
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log


async def list_call_logs(lead_id: int, limit: int = 5) -> List[CallLog]:
    async with AsyncSession(engine) as session:
        stmt = (
            select(CallLog)
            .where(CallLog.lead_id == lead_id)
            .order_by(desc(CallLog.created_at))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()
