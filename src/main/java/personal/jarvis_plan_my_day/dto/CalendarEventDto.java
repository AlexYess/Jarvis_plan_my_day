package personal.jarvis_plan_my_day.dto;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public record CalendarEventDto(
        String kind,
        String etag,
        String id,
        String status,
        String htmlLink,
        OffsetDateTime created,
        OffsetDateTime updated,
        String summary,
        String description,
        String location,
        String colorId,
        UserDto creator,
        UserDto organizer,
        EventDateTimeDto start,
        EventDateTimeDto end,
        Boolean endTimeUnspecified,
        List<String> recurrence,
        String recurringEventId,
        EventDateTimeDto originalStartTime,
        String transparency,
        String visibility,
        String iCalUID,
        Integer sequence,
        List<AttendeeDto> attendees,
        Boolean attendeesOmitted,
        ExtendedPropertiesDto extendedProperties,
        String hangoutLink,
        ConferenceDataDto conferenceData,
        GadgetDto gadget,
        Boolean anyoneCanAddSelf,
        Boolean guestsCanInviteOthers,
        Boolean guestsCanModify,
        Boolean guestsCanSeeOtherGuests,
        Boolean privateCopy,
        Boolean locked,
        RemindersDto reminders,
        SourceDto source,
        WorkingLocationPropertiesDto workingLocationProperties,
        OutOfOfficePropertiesDto outOfOfficeProperties,
        FocusTimePropertiesDto focusTimeProperties,
        List<AttachmentDto> attachments,
        BirthdayPropertiesDto birthdayProperties,
        String eventType
) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record UserDto(
            String id,
            String email,
            String displayName,
            Boolean self
    ) {}

    public record EventDateTimeDto(
            LocalDate date,
            OffsetDateTime dateTime,
            String timeZone
    ) {}

    public record AttendeeDto(
            String id,
            String email,
            String displayName,
            Boolean organizer,
            Boolean self,
            Boolean resource,
            Boolean optional,
            String responseStatus,
            String comment,
            Integer additionalGuests
    ) {}

    public record ExtendedPropertiesDto(
            @JsonProperty("private")
            Map<String, String> privateProperties,
            Map<String, String> shared
    ) {}

    public record ConferenceDataDto(
            CreateRequestDto createRequest,
            List<EntryPointDto> entryPoints,
            ConferenceSolutionDto conferenceSolution,
            String conferenceId,
            String signature,
            String notes
    ) {}

    public record CreateRequestDto(
            String requestId,
            ConferenceSolutionKeyDto conferenceSolutionKey,
            ConferenceStatusDto status
    ) {}

    public record ConferenceSolutionKeyDto(
            String type
    ) {}

    public record ConferenceStatusDto(
            String statusCode
    ) {}

    public record EntryPointDto(
            String entryPointType,
            String uri,
            String label,
            String pin,
            String accessCode,
            String meetingCode,
            String passcode,
            String password
    ) {}

    public record ConferenceSolutionDto(
            ConferenceSolutionKeyDto key,
            String name,
            String iconUri
    ) {}

    public record GadgetDto(
            String type,
            String title,
            String link,
            String iconLink,
            Integer width,
            Integer height,
            String display,
            Map<String, String> preferences
    ) {}

    public record RemindersDto(
            Boolean useDefault,
            List<ReminderOverrideDto> overrides
    ) {}

    public record ReminderOverrideDto(
            String method,
            Integer minutes
    ) {}

    public record SourceDto(
            String url,
            String title
    ) {}

    public record WorkingLocationPropertiesDto(
            String type,
            Object homeOffice,
            CustomLocationDto customLocation,
            OfficeLocationDto officeLocation
    ) {}

    public record CustomLocationDto(
            String label
    ) {}

    public record OfficeLocationDto(
            String buildingId,
            String floorId,
            String floorSectionId,
            String deskId,
            String label
    ) {}

    public record OutOfOfficePropertiesDto(
            String autoDeclineMode,
            String declineMessage
    ) {}

    public record FocusTimePropertiesDto(
            String autoDeclineMode,
            String declineMessage,
            String chatStatus
    ) {}

    public record AttachmentDto(
            String fileUrl,
            String title,
            String mimeType,
            String iconLink,
            String fileId
    ) {}

    public record BirthdayPropertiesDto(
            String contact,
            String type,
            String customTypeName
    ) {}
}