package personal.jarvis_plan_my_day.dto;

import java.util.List;

public record PatternAnalysisResponseDto(
        List<BehaviorPatternDto> patterns
) {
}