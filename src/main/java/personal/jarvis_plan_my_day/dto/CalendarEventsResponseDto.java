package personal.jarvis_plan_my_day.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import personal.jarvis_plan_my_day.dto.CalendarEventDto.ReminderOverrideDto;

import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public record CalendarEventsResponseDto(
        String kind,
        String etag,
        String summary,
        String description,
        String updated,
        String timeZone,
        String accessRole,
        List<ReminderOverrideDto> defaultReminders,  // ← было List<String>
        String nextPageToken,
        String nextSyncToken,
        List<CalendarEventDto> items
) {}