from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
import uuid

from ..database import get_db
from ..models import Department, User
from ..schemas import DepartmentCreate, DepartmentUpdate, DepartmentOut
from ..security import require_admin, require_any
from ..utils.audit import get_client_ip, record_audit

router = APIRouter(prefix="/api/departments", tags=["departments"])


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
    record_audit(
        db,
        user_id=current_user.id,
        action="CREATE_DEPARTMENT",
        resource="department",
        resource_id=dept.id,
        detail=f"Created: {dept.name}",
        ip=get_client_ip(request),
    )
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
    record_audit(
        db,
        user_id=current_user.id,
        action="UPDATE_DEPARTMENT",
        resource="department",
        resource_id=dept.id,
        detail=f"Updated: {dept.name}",
        ip=get_client_ip(request),
    )
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
    record_audit(
        db,
        user_id=current_user.id,
        action="DELETE_DEPARTMENT",
        resource="department",
        resource_id=dept.id,
        detail=f"Deleted: {dept.name}",
        ip=get_client_ip(request),
    )
    db.delete(dept)
    db.commit()
