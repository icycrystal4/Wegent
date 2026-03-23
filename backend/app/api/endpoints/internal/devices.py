# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Internal device APIs for service-to-service communication."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.endpoints.devices import DeviceSandboxExecResponse

router = APIRouter(prefix="/devices", tags=["internal-devices"])


class InternalDeviceSandboxExecRequest(BaseModel):
    """Internal request model for device-backed command execution."""

    task_id: int | None = Field(default=None, ge=1, description="Optional task ID")
    user_id: int = Field(..., ge=1, description="Owner user ID")
    command: str = Field(..., min_length=1, description="Command to execute")
    working_dir: str = Field(
        default="/home/user",
        description="Working directory for command execution",
    )
    timeout_seconds: int = Field(
        default=300,
        ge=1,
        le=1800,
        description="Command timeout in seconds",
    )
    required_capability: str | None = Field(
        default=None,
        description="Optional device capability required for routing",
    )
    device_id: str | None = Field(
        default=None,
        description="Optional explicit device ID override",
    )


class InternalTaskSandboxBindingResponse(BaseModel):
    """Current sticky sandbox binding for a task."""

    backend: str | None = None
    device_id: str | None = None


class InternalDeviceSandboxReadFileRequest(BaseModel):
    """Internal request model for device-backed file reads."""

    task_id: int | None = Field(default=None, ge=1, description="Optional task ID")
    user_id: int = Field(..., ge=1, description="Owner user ID")
    file_path: str = Field(..., min_length=1, description="Path to read")
    format: str = Field(default="text", description="Read format: text or bytes")
    device_id: str | None = Field(
        default=None, description="Optional explicit device ID override"
    )


class InternalDeviceSandboxListFilesRequest(BaseModel):
    """Internal request model for device-backed file listing."""

    task_id: int | None = Field(default=None, ge=1, description="Optional task ID")
    user_id: int = Field(..., ge=1, description="Owner user ID")
    path: str = Field(default="/home/user", description="Directory to list")
    depth: int = Field(default=1, ge=1, le=10, description="Listing depth")
    device_id: str | None = Field(
        default=None, description="Optional explicit device ID override"
    )


class InternalDeviceSandboxWriteFileRequest(BaseModel):
    """Internal request model for device-backed file writes."""

    task_id: int | None = Field(default=None, ge=1, description="Optional task ID")
    user_id: int = Field(..., ge=1, description="Owner user ID")
    file_path: str = Field(..., min_length=1, description="Path to write")
    content: str = Field(..., description="File content")
    format: str = Field(default="text", description="Write format: text or bytes")
    create_dirs: bool = Field(
        default=True, description="Create parent directories automatically"
    )
    device_id: str | None = Field(
        default=None, description="Optional explicit device ID override"
    )


class InternalDeviceSandboxDownloadAttachmentRequest(BaseModel):
    """Internal request model for device-backed attachment downloads."""

    task_id: int | None = Field(default=None, ge=1, description="Optional task ID")
    user_id: int = Field(..., ge=1, description="Owner user ID")
    attachment_url: str = Field(
        ..., min_length=1, description="Attachment download URL"
    )
    save_path: str = Field(..., min_length=1, description="Destination path on device")
    auth_token: str = Field(..., min_length=1, description="Task or user auth token")
    api_base_url: str = Field(..., min_length=1, description="Backend base URL")
    timeout_seconds: int = Field(
        default=300, ge=1, le=1800, description="Download timeout in seconds"
    )
    device_id: str | None = Field(
        default=None, description="Optional explicit device ID override"
    )


class InternalDeviceSandboxUploadAttachmentRequest(BaseModel):
    """Internal request model for device-backed attachment uploads."""

    task_id: int | None = Field(default=None, ge=1, description="Optional task ID")
    user_id: int = Field(..., ge=1, description="Owner user ID")
    file_path: str = Field(..., min_length=1, description="Path to the local file")
    auth_token: str = Field(..., min_length=1, description="Task or user auth token")
    api_base_url: str = Field(..., min_length=1, description="Backend base URL")
    overwrite_attachment_id: int | None = Field(
        default=None, ge=1, description="Optional attachment to overwrite"
    )
    timeout_seconds: int = Field(
        default=300, ge=1, le=1800, description="Upload timeout in seconds"
    )
    device_id: str | None = Field(
        default=None, description="Optional explicit device ID override"
    )


class DeviceSandboxGenericResponse(BaseModel):
    """Generic response model for device-backed sandbox file helpers."""

    success: bool = Field(..., description="Whether the operation succeeded")
    device_id: str = Field(..., description="Device that executed the operation")
    backend: str = Field(default="device", description="Execution backend identifier")
    execution_time: float = Field(..., description="Execution time in seconds")
    data: dict[str, Any] = Field(
        default_factory=dict, description="Operation-specific payload"
    )


def _build_generic_response(result: dict[str, Any]) -> DeviceSandboxGenericResponse:
    """Convert a device sandbox service response into the generic endpoint model."""
    payload = dict(result)
    return DeviceSandboxGenericResponse(
        success=bool(payload.pop("success", False)),
        device_id=str(payload.pop("device_id")),
        backend=str(payload.pop("backend", "device")),
        execution_time=float(payload.pop("execution_time", 0.0)),
        data=payload,
    )


@router.post("/sandbox/exec", response_model=DeviceSandboxExecResponse)
async def execute_device_sandbox_command_internal(
    request: InternalDeviceSandboxExecRequest,
    db: Session = Depends(get_db),
) -> DeviceSandboxExecResponse:
    """Execute a command on a user's device for internal trusted services."""
    from app.services.device_sandbox_service import (
        DeviceSandboxError,
        device_sandbox_service,
    )

    try:
        result = await device_sandbox_service.execute_command(
            db=db,
            task_id=request.task_id,
            user_id=request.user_id,
            command=request.command,
            working_dir=request.working_dir,
            timeout_seconds=request.timeout_seconds,
            required_capability=request.required_capability,
            device_id=request.device_id,
        )
    except DeviceSandboxError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    db.commit()
    return DeviceSandboxExecResponse(**result)


@router.get(
    "/sandbox/binding/{task_id}", response_model=InternalTaskSandboxBindingResponse
)
async def get_task_sandbox_binding(
    task_id: int,
    user_id: int,
    db: Session = Depends(get_db),
) -> InternalTaskSandboxBindingResponse:
    """Return the sticky sandbox binding currently stored on the task."""
    from app.models.task import TaskResource
    from app.services.device_sandbox_service import (
        DEVICE_BACKEND_NAME,
        SANDBOX_BACKEND_LABEL,
        SANDBOX_DEVICE_ID_LABEL,
    )

    task = (
        db.query(TaskResource)
        .filter(
            TaskResource.id == task_id,
            TaskResource.user_id == user_id,
            TaskResource.kind == "Task",
            TaskResource.is_active == TaskResource.STATE_ACTIVE,
        )
        .first()
    )
    if not task:
        return InternalTaskSandboxBindingResponse()

    task_json = task.json if isinstance(task.json, dict) else {}
    labels = task_json.get("metadata", {}).get("labels", {})
    backend = labels.get(SANDBOX_BACKEND_LABEL)
    device_id = labels.get(SANDBOX_DEVICE_ID_LABEL)
    if backend != DEVICE_BACKEND_NAME or not device_id:
        return InternalTaskSandboxBindingResponse()

    return InternalTaskSandboxBindingResponse(backend=backend, device_id=device_id)


@router.post("/sandbox/read-file", response_model=DeviceSandboxGenericResponse)
async def read_device_sandbox_file_internal(
    request: InternalDeviceSandboxReadFileRequest,
    db: Session = Depends(get_db),
) -> DeviceSandboxGenericResponse:
    """Read a file from the bound device-backed sandbox."""
    from app.services.device_sandbox_service import (
        DeviceSandboxError,
        device_sandbox_service,
    )

    try:
        result = await device_sandbox_service.read_file(
            db=db,
            user_id=request.user_id,
            task_id=request.task_id,
            file_path=request.file_path,
            format=request.format,
            device_id=request.device_id,
        )
    except DeviceSandboxError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    db.commit()
    return _build_generic_response(result)


@router.post("/sandbox/list-files", response_model=DeviceSandboxGenericResponse)
async def list_device_sandbox_files_internal(
    request: InternalDeviceSandboxListFilesRequest,
    db: Session = Depends(get_db),
) -> DeviceSandboxGenericResponse:
    """List files from the bound device-backed sandbox."""
    from app.services.device_sandbox_service import (
        DeviceSandboxError,
        device_sandbox_service,
    )

    try:
        result = await device_sandbox_service.list_files(
            db=db,
            user_id=request.user_id,
            task_id=request.task_id,
            path=request.path,
            depth=request.depth,
            device_id=request.device_id,
        )
    except DeviceSandboxError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    db.commit()
    return _build_generic_response(result)


@router.post("/sandbox/write-file", response_model=DeviceSandboxGenericResponse)
async def write_device_sandbox_file_internal(
    request: InternalDeviceSandboxWriteFileRequest,
    db: Session = Depends(get_db),
) -> DeviceSandboxGenericResponse:
    """Write a file into the bound device-backed sandbox."""
    from app.services.device_sandbox_service import (
        DeviceSandboxError,
        device_sandbox_service,
    )

    try:
        result = await device_sandbox_service.write_file(
            db=db,
            user_id=request.user_id,
            task_id=request.task_id,
            file_path=request.file_path,
            content=request.content,
            format=request.format,
            create_dirs=request.create_dirs,
            device_id=request.device_id,
        )
    except DeviceSandboxError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    db.commit()
    return _build_generic_response(result)


@router.post(
    "/sandbox/download-attachment", response_model=DeviceSandboxGenericResponse
)
async def download_device_sandbox_attachment_internal(
    request: InternalDeviceSandboxDownloadAttachmentRequest,
    db: Session = Depends(get_db),
) -> DeviceSandboxGenericResponse:
    """Download a Wegent attachment into the bound device-backed sandbox."""
    from app.services.device_sandbox_service import (
        DeviceSandboxError,
        device_sandbox_service,
    )

    try:
        result = await device_sandbox_service.download_attachment(
            db=db,
            user_id=request.user_id,
            task_id=request.task_id,
            attachment_url=request.attachment_url,
            save_path=request.save_path,
            auth_token=request.auth_token,
            api_base_url=request.api_base_url,
            timeout_seconds=request.timeout_seconds,
            device_id=request.device_id,
        )
    except DeviceSandboxError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    db.commit()
    return _build_generic_response(result)


@router.post("/sandbox/upload-attachment", response_model=DeviceSandboxGenericResponse)
async def upload_device_sandbox_attachment_internal(
    request: InternalDeviceSandboxUploadAttachmentRequest,
    db: Session = Depends(get_db),
) -> DeviceSandboxGenericResponse:
    """Upload a device-local file through the bound device-backed sandbox."""
    from app.services.device_sandbox_service import (
        DeviceSandboxError,
        device_sandbox_service,
    )

    try:
        result = await device_sandbox_service.upload_attachment(
            db=db,
            user_id=request.user_id,
            task_id=request.task_id,
            file_path=request.file_path,
            auth_token=request.auth_token,
            api_base_url=request.api_base_url,
            overwrite_attachment_id=request.overwrite_attachment_id,
            timeout_seconds=request.timeout_seconds,
            device_id=request.device_id,
        )
    except DeviceSandboxError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    db.commit()
    return _build_generic_response(result)
