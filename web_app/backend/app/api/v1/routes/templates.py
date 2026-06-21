from fastapi import APIRouter, HTTPException

from app.services.template_service import get_template, list_templates


router = APIRouter()


@router.get("")
def get_templates() -> dict:
    return list_templates()


@router.get("/{template_id}")
def get_template_by_id(template_id: str) -> dict:
    template = get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    return template
