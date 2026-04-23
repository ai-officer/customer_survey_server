from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
import uuid

from ..database import get_db
from ..models import Department, AuditLog, User
from ..schemas import DepartmentCreate, DepartmentUpdate, DepartmentOut
from ..security import require_admin, require_any

router = APIRouter(prefix="/api/departments", tags=["departments"])


def _log(db, user_id, action, resource_id, detail, ip):
    db.add(AuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action=action,
        resource="department",
        resource_id=resource_id,
        detail=detail,
        ip_address=ip,
    ))


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("", response_model=list[DepartmentOut])
def list_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any),
):
    depts = db.query(Department).order_by(Department.name.asc()).all()
    return [DepartmentOut.from_orm_department(d) for d in depts]


@router.post("", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Department name is required")
    existing = db.query(Department).filter(Department.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Department already exists")

    dept = Department(id=str(uuid.uuid4()), name=name)
    db.add(dept)
    db.flush()
    _log(db, current_user.id, "CREATE_DEPARTMENT", dept.id, f"Created: {dept.name}", _ip(request))
    db.commit()
    db.refresh(dept)
    return DepartmentOut.from_orm_department(dept)


@router.put("/{department_id}", response_model=DepartmentOut)
def update_department(
    department_id: str,
    payload: DepartmentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    if payload.name is not None:
        new_name = payload.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Department name cannot be empty")
        if db.query(Department).filter(Department.name == new_name, Department.id != department_id).first():
            raise HTTPException(status_code=400, detail="Another department with this name already exists")
        dept.name = new_name
    _log(db, current_user.id, "UPDATE_DEPARTMENT", dept.id, f"Updated: {dept.name}", _ip(request))
    db.commit()
    db.refresh(dept)
    return DepartmentOut.from_orm_department(dept)


@router.delete("/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department(
    department_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    _log(db, current_user.id, "DELETE_DEPARTMENT", dept.id, f"Deleted: {dept.name}", _ip(request))
    db.delete(dept)
    db.commit()
