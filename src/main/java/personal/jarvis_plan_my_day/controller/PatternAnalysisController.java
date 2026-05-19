package personal.jarvis_plan_my_day.controller;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import personal.jarvis_plan_my_day.dto.CalendarEventDto;
import personal.jarvis_plan_my_day.service.GoogleCalendarService;
import personal.jarvis_plan_my_day.service.PatternAnalyzerService;

import java.util.List;
import java.util.Map;

@RestController
public class PatternAnalysisController {

    private final GoogleCalendarService googleCalendarService;
    private final PatternAnalyzerService patternAnalyzerService;

    public PatternAnalysisController(
            GoogleCalendarService googleCalendarService,
            PatternAnalyzerService PatternAnalyzerService
    ) {
        this.googleCalendarService = googleCalendarService;
        this.patternAnalyzerService = PatternAnalyzerService;
    }

    @GetMapping("/api/patterns/analyze")
    public Map<String, Object> analyzeEvents(
            @RegisteredOAuth2AuthorizedClient("google") OAuth2AuthorizedClient authorizedClient,
            @RequestParam(defaultValue = "30") int days
    ) {
        List<CalendarEventDto> events =
                googleCalendarService.getEventsForLastDays(authorizedClient, days);

        Long userId = 1L;

        return patternAnalyzerService.analyzeEvents(userId, events);
    }
}