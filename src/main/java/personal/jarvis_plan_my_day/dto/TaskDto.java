package personal.jarvis_plan_my_day.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.time.OffsetDateTime;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public record TaskDto(
        String kind,
        String id,
        String etag,
        String title,
        OffsetDateTime updated,
        String selfLink,
        String parent,
        String position,
        String notes,
        String status,           // "needsAction" или "completed"
        OffsetDateTime due,
        OffsetDateTime completed,
        Boolean deleted,
        Boolean hidden,
        List<TaskLinkDto> links,
        String webViewLink,
        AssignmentInfoDto assignmentInfo
) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record TaskLinkDto(
            String type,
            String description,
            String link
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record AssignmentInfoDto(
            String linkToTask,
            String surfaceType
    ) {}
}