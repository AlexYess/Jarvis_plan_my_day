"""
Pydantic models that mirror the Java CalendarEventDto structure.
Field names use camelCase to match Java JSON serialization directly.
Reserved Python keywords (`self`, `private`) are aliased.
"""

from datetime import datetime
from datetime import date as DateType
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


_BASE_CONFIG = ConfigDict(populate_by_name=True, extra="ignore")


class UserDto(BaseModel):
    model_config = _BASE_CONFIG
    id: Optional[str] = None
    email: Optional[str] = None
    displayName: Optional[str] = None
    self_: Optional[bool] = Field(default=None, alias="self")


class EventDateTimeDto(BaseModel):
    model_config = _BASE_CONFIG
    date: Optional[DateType] = None
    dateTime: Optional[datetime] = None
    timeZone: Optional[str] = None


class AttendeeDto(BaseModel):
    model_config = _BASE_CONFIG
    id: Optional[str] = None
    email: Optional[str] = None
    displayName: Optional[str] = None
    organizer: Optional[bool] = None
    self_: Optional[bool] = Field(default=None, alias="self")
    resource: Optional[bool] = None
    optional: Optional[bool] = None
    responseStatus: Optional[str] = None
    comment: Optional[str] = None
    additionalGuests: Optional[int] = None


class ExtendedPropertiesDto(BaseModel):
    model_config = _BASE_CONFIG
    privateProperties: Optional[Dict[str, str]] = Field(default=None, alias="private")
    shared: Optional[Dict[str, str]] = None


class ConferenceSolutionKeyDto(BaseModel):
    model_config = _BASE_CONFIG
    type: Optional[str] = None


class ConferenceStatusDto(BaseModel):
    model_config = _BASE_CONFIG
    statusCode: Optional[str] = None


class CreateRequestDto(BaseModel):
    model_config = _BASE_CONFIG
    requestId: Optional[str] = None
    conferenceSolutionKey: Optional[ConferenceSolutionKeyDto] = None
    status: Optional[ConferenceStatusDto] = None


class EntryPointDto(BaseModel):
    model_config = _BASE_CONFIG
    entryPointType: Optional[str] = None
    uri: Optional[str] = None
    label: Optional[str] = None
    pin: Optional[str] = None
    accessCode: Optional[str] = None
    meetingCode: Optional[str] = None
    passcode: Optional[str] = None
    password: Optional[str] = None


class ConferenceSolutionDto(BaseModel):
    model_config = _BASE_CONFIG
    key: Optional[ConferenceSolutionKeyDto] = None
    name: Optional[str] = None
    iconUri: Optional[str] = None


class ConferenceDataDto(BaseModel):
    model_config = _BASE_CONFIG
    createRequest: Optional[CreateRequestDto] = None
    entryPoints: Optional[List[EntryPointDto]] = None
    conferenceSolution: Optional[ConferenceSolutionDto] = None
    conferenceId: Optional[str] = None
    signature: Optional[str] = None
    notes: Optional[str] = None


class GadgetDto(BaseModel):
    model_config = _BASE_CONFIG
    type: Optional[str] = None
    title: Optional[str] = None
    link: Optional[str] = None
    iconLink: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    display: Optional[str] = None
    preferences: Optional[Dict[str, str]] = None


class ReminderOverrideDto(BaseModel):
    model_config = _BASE_CONFIG
    method: Optional[str] = None
    minutes: Optional[int] = None


class RemindersDto(BaseModel):
    model_config = _BASE_CONFIG
    useDefault: Optional[bool] = None
    overrides: Optional[List[ReminderOverrideDto]] = None


class SourceDto(BaseModel):
    model_config = _BASE_CONFIG
    url: Optional[str] = None
    title: Optional[str] = None


class CustomLocationDto(BaseModel):
    model_config = _BASE_CONFIG
    label: Optional[str] = None


class OfficeLocationDto(BaseModel):
    model_config = _BASE_CONFIG
    buildingId: Optional[str] = None
    floorId: Optional[str] = None
    floorSectionId: Optional[str] = None
    deskId: Optional[str] = None
    label: Optional[str] = None


class WorkingLocationPropertiesDto(BaseModel):
    model_config = _BASE_CONFIG
    type: Optional[str] = None
    homeOffice: Optional[Any] = None
    customLocation: Optional[CustomLocationDto] = None
    officeLocation: Optional[OfficeLocationDto] = None


class OutOfOfficePropertiesDto(BaseModel):
    model_config = _BASE_CONFIG
    autoDeclineMode: Optional[str] = None
    declineMessage: Optional[str] = None


class FocusTimePropertiesDto(BaseModel):
    model_config = _BASE_CONFIG
    autoDeclineMode: Optional[str] = None
    declineMessage: Optional[str] = None
    chatStatus: Optional[str] = None


class AttachmentDto(BaseModel):
    model_config = _BASE_CONFIG
    fileUrl: Optional[str] = None
    title: Optional[str] = None
    mimeType: Optional[str] = None
    iconLink: Optional[str] = None
    fileId: Optional[str] = None


class BirthdayPropertiesDto(BaseModel):
    model_config = _BASE_CONFIG
    contact: Optional[str] = None
    type: Optional[str] = None
    customTypeName: Optional[str] = None


class CalendarEventDto(BaseModel):
    model_config = _BASE_CONFIG

    kind: Optional[str] = None
    etag: Optional[str] = None
    id: Optional[str] = None
    status: Optional[str] = None
    htmlLink: Optional[str] = None
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    colorId: Optional[str] = None
    creator: Optional[UserDto] = None
    organizer: Optional[UserDto] = None
    start: Optional[EventDateTimeDto] = None
    end: Optional[EventDateTimeDto] = None
    endTimeUnspecified: Optional[bool] = None
    recurrence: Optional[List[str]] = None
    recurringEventId: Optional[str] = None
    originalStartTime: Optional[EventDateTimeDto] = None
    transparency: Optional[str] = None
    visibility: Optional[str] = None
    iCalUID: Optional[str] = None
    sequence: Optional[int] = None
    attendees: Optional[List[AttendeeDto]] = None
    attendeesOmitted: Optional[bool] = None
    extendedProperties: Optional[ExtendedPropertiesDto] = None
    hangoutLink: Optional[str] = None
    conferenceData: Optional[ConferenceDataDto] = None
    gadget: Optional[GadgetDto] = None
    anyoneCanAddSelf: Optional[bool] = None
    guestsCanInviteOthers: Optional[bool] = None
    guestsCanModify: Optional[bool] = None
    guestsCanSeeOtherGuests: Optional[bool] = None
    privateCopy: Optional[bool] = None
    locked: Optional[bool] = None
    reminders: Optional[RemindersDto] = None
    source: Optional[SourceDto] = None
    workingLocationProperties: Optional[WorkingLocationPropertiesDto] = None
    outOfOfficeProperties: Optional[OutOfOfficePropertiesDto] = None
    focusTimeProperties: Optional[FocusTimePropertiesDto] = None
    attachments: Optional[List[AttachmentDto]] = None
    birthdayProperties: Optional[BirthdayPropertiesDto] = None
    eventType: Optional[str] = None


class PatternAnalysisRequest(BaseModel):
    """Wrapper that Java sends: {"userId": ..., "events": [...]}"""
    model_config = _BASE_CONFIG
    userId: int
    events: List[CalendarEventDto]


# ============================================================================
# Tag management (Layer 2 taxonomy)
# ============================================================================

class TagDto(BaseModel):
    """A single tag in the taxonomy."""
    model_config = _BASE_CONFIG
    id: int
    name: str
    description: Optional[str] = None
    parent_name: Optional[str] = None
    created_at: datetime


class CreateTagRequest(BaseModel):
    """Request to add a new tag to the taxonomy."""
    model_config = _BASE_CONFIG
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    parent_name: Optional[str] = Field(None, max_length=100)


# ============================================================================
# Event classification (Layer 2 LLM)
# ============================================================================

class ClassifyEventsRequest(BaseModel):
    """List of event titles to classify. Duplicates handled by service."""
    model_config = _BASE_CONFIG
    titles: List[str]
    force_refresh: bool = False


class TagScore(BaseModel):
    model_config = _BASE_CONFIG
    tag: str
    confidence: float


# ============================================================================
# Google Tasks DTOs (mirror of Java TaskDto)
# ============================================================================

class TaskLinkDto(BaseModel):
    model_config = _BASE_CONFIG
    type: Optional[str] = None
    description: Optional[str] = None
    link: Optional[str] = None


class AssignmentInfoDto(BaseModel):
    model_config = _BASE_CONFIG
    linkToTask: Optional[str] = None
    surfaceType: Optional[str] = None


class TaskDto(BaseModel):
    """Mirror of Java TaskDto. All fields optional since Google omits absent ones."""
    model_config = _BASE_CONFIG
    kind: Optional[str] = None
    id: Optional[str] = None
    etag: Optional[str] = None
    title: Optional[str] = None
    updated: Optional[datetime] = None
    selfLink: Optional[str] = None
    parent: Optional[str] = None
    position: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    due: Optional[datetime] = None
    completed: Optional[datetime] = None
    deleted: Optional[bool] = None
    hidden: Optional[bool] = None
    links: Optional[List[TaskLinkDto]] = None
    webViewLink: Optional[str] = None
    assignmentInfo: Optional[AssignmentInfoDto] = None


class ClassifyTasksRequest(BaseModel):
    """Wrapper sent from Java: list of full Google Task objects."""
    model_config = _BASE_CONFIG
    tasks: List[TaskDto]
    force_refresh: bool = False