package personal.jarvis_plan_my_day.dto;

public record BehaviorPatternDto(
    String title, String description, Double confidence, Integer sampleSize) {}
