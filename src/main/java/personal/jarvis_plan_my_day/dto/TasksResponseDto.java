package personal.jarvis_plan_my_day.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public record TasksResponseDto(
        String kind,
        String etag,
        String nextPageToken,
        List<TaskDto> items
) {}