from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.fmu_library import FMULibrary

router = APIRouter(prefix="/api/fmu-library", tags=["fmu-library"])


class FMUListItem(BaseModel):
    model_config = {"from_attributes": True}

    type_name: str
    version: str


class FMUDetail(BaseModel):
    model_config = {"from_attributes": True}

    type_name: str
    version: str
    fmu_path: str
    manifest: dict


class FMURegister(BaseModel):
    type_name: str
    version: str
    fmu_path: str
    manifest: dict


@router.get("", response_model=list[FMUListItem])
async def list_fmus(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FMULibrary).order_by(FMULibrary.type_name))
    return result.scalars().all()


@router.get("/{type_name}/manifest")
async def get_manifest(type_name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FMULibrary).where(FMULibrary.type_name == type_name)
    )
    fmu = result.scalar_one_or_none()
    if not fmu:
        raise HTTPException(status_code=404, detail=f"FMU type '{type_name}' not found")
    return fmu.manifest


@router.post("", response_model=FMUDetail, status_code=status.HTTP_201_CREATED)
async def register_fmu(body: FMURegister, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(FMULibrary).where(FMULibrary.type_name == body.type_name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"FMU type '{body.type_name}' already exists")

    fmu = FMULibrary(
        type_name=body.type_name,
        version=body.version,
        fmu_path=body.fmu_path,
        manifest=body.manifest,
    )
    db.add(fmu)
    await db.flush()
    await db.refresh(fmu)
    return fmu
