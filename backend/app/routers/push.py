"""Subskrypcje Web Push (api.md, sekcja 6). Pushe dostaje tylko leśniczy."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.deps import CurrentUser, require_role
from app.models import PushSubscription, User
from app.schemas import PushSubscriptionIn, PushSubscriptionOut, VapidKeyOut

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/push", tags=["push"])

Session = Annotated[AsyncSession, Depends(get_session)]
Forester = Annotated[User, Depends(require_role("forester"))]


@router.get(
    "/vapid-public-key",
    response_model=VapidKeyOut,
    responses={503: {"description": "Powiadomienia nie są skonfigurowane na serwerze"}},
)
async def vapid_public_key(_: CurrentUser) -> VapidKeyOut:
    """Klucz do `pushManager.subscribe({ applicationServerKey })`."""
    if not settings.vapid_public_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Powiadomienia nie są skonfigurowane"
        )
    return VapidKeyOut(public_key=settings.vapid_public_key)


@router.post(
    "/subscriptions",
    response_model=PushSubscriptionOut,
    status_code=status.HTTP_201_CREATED,
    responses={403: {"description": "Tylko leśniczy dostaje powiadomienia"}},
)
async def save_subscription(
    body: PushSubscriptionIn, user: Forester, session: Session
) -> PushSubscriptionOut:
    """Ten sam `endpoint` wysłany ponownie nadpisuje klucze i właściciela, bez duplikatu."""
    subscription = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    if subscription is None:
        subscription = PushSubscription(endpoint=body.endpoint)
        session.add(subscription)
    subscription.p256dh = body.keys.p256dh
    subscription.auth = body.keys.auth
    subscription.user_id = user.id
    subscription.device_label = body.device_label
    await session.commit()
    log.info(
        "Subskrypcja push: %s, urządzenie %s", user.login, body.device_label or "-"
    )
    return PushSubscriptionOut(id=subscription.id)


@router.delete("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    endpoint: Annotated[str, Query(min_length=1, max_length=2000)],
    user: CurrentUser,
    session: Session,
) -> Response:
    """Przy wylogowaniu. 204 także wtedy, gdy subskrypcji nie ma; cudzej nie usuwa."""
    await session.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == endpoint, PushSubscription.user_id == user.id
        )
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
