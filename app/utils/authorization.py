"""Permission helpers shared by routers."""
from typing import Optional

from fastapi import HTTPException, status

from ..models import User, UserRole


def ensure_owner_or_admin(
    user: User,
    resource_owner_id: Optional[str],
    *,
    message: str = "You can only access this resource you created",
) -> None:
    """Raise 403 unless `user` is admin or `user.id == resource_owner_id`.

    Use at the top of update / delete / read-detail handlers."""
    if user.role == UserRole.admin:
        return
    if user.id == resource_owner_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=message,
    )
