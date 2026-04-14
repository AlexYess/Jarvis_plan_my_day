package personal.jarvis_plan_my_day.controller;

import personal.jarvis_plan_my_day.dto.CalendarEventDto;
import personal.jarvis_plan_my_day.dto.TaskDto;
import personal.jarvis_plan_my_day.service.GoogleCalendarService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import personal.jarvis_plan_my_day.service.GoogleTaskService;

import java.util.List;

@RestController
public class CalendarController {

  private final GoogleCalendarService googleCalendarService;
  private final GoogleTaskService googleTaskService;

  public CalendarController(GoogleCalendarService googleCalendarService, GoogleTaskService googleTaskService) {
    this.googleCalendarService = googleCalendarService;
    this.googleTaskService = googleTaskService;
  }

  @GetMapping("/")
  public String home() {
    return """
            <h2>Jarvis Plan My Day</h2>
            <a href="/calendar/today">Получить события на сегодня</a>
            <a href="/tasks">Получить задачи</a>
            """;
  }

  @GetMapping("/calendar/today")
  public List<CalendarEventDto> getTodayEvents(
      @RegisteredOAuth2AuthorizedClient("google") OAuth2AuthorizedClient authorizedClient) {
    return googleCalendarService.getTodayEvents(authorizedClient);
  }

  @GetMapping("/tasks")
  public List<TaskDto> getTasks(
      @RegisteredOAuth2AuthorizedClient("google") OAuth2AuthorizedClient authorizedClient) {
    return googleTaskService.getTasks(authorizedClient);
  }
}
