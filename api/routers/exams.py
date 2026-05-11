"""Exams router — CRUD for exam definitions and scheduling."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.exam import Exam
from api.schemas.exam import ExamCreate, ExamUpdate, ExamResponse, ExamListResponse

router = APIRouter(prefix="/api/exams", tags=["exams"])


@router.post("/", response_model=ExamResponse, status_code=status.HTTP_201_CREATED)
async def create_exam(data: ExamCreate, db: AsyncSession = Depends(get_db)):
    """Create a new exam."""
    exam = Exam(**data.model_dump())
    db.add(exam)
    await db.flush()
    await db.refresh(exam)
    return exam


@router.get("/", response_model=ExamListResponse)
async def list_exams(db: AsyncSession = Depends(get_db)):
    """List all exams."""
    result = await db.execute(select(Exam).order_by(Exam.created_at.desc()))
    exams = list(result.scalars().all())
    return ExamListResponse(exams=exams, total=len(exams))


@router.get("/{exam_id}", response_model=ExamResponse)
async def get_exam(exam_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get exam details."""
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    return exam


@router.patch("/{exam_id}", response_model=ExamResponse)
async def update_exam(
    exam_id: uuid.UUID, data: ExamUpdate, db: AsyncSession = Depends(get_db)
):
    """Update exam settings."""
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(exam, field, value)
    await db.flush()
    await db.refresh(exam)
    return exam


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam(exam_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete an exam."""
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    await db.delete(exam)
