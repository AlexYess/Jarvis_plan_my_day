package personal.jarvis_plan_my_day.service;

import org.springframework.web.client.HttpClientErrorException;
import personal.jarvis_plan_my_day.dto.CalendarEventDto;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Service
public class GoogleCalendarService {

  private final RestClient restClient;

  public GoogleCalendarService() {
    this.restClient =
        RestClient.builder().baseUrl("https://www.googleapis.com/calendar/v3").build();
  }

  public List<CalendarEventDto> getTodayEvents(OAuth2AuthorizedClient authorizedClient) {
    String accessToken = authorizedClient.getAccessToken().getTokenValue();

    ZoneId zoneId = ZoneId.systemDefault();
    ZonedDateTime startOfDay = ZonedDateTime.now(zoneId).toLocalDate().atStartOfDay(zoneId);
    ZonedDateTime endOfDay = startOfDay.plusDays(1);

    // Переводим в UTC, чтобы получить строки с 'Z' вместо '+02:00'
    String timeMin = startOfDay.toInstant().toString();
    String timeMax = endOfDay.toInstant().toString();

    try {
      Map<String, Object> response =
          restClient
              .get()
              .uri(
                  uriBuilder ->
                      uriBuilder
                          .path("/calendars/{calendarId}/events")
                          .queryParam("timeMin", timeMin)
                          .queryParam("timeMax", timeMax)
                          .queryParam("singleEvents", "true")
                          .queryParam("orderBy", "startTime")
                          .build("primary"))
              .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
              .retrieve()
              .body(Map.class);

      return mapEvents(response);

    } catch (HttpClientErrorException e) {
      System.out.println("Google Calendar API error: " + e.getStatusCode());
      System.out.println("Response body: " + e.getResponseBodyAsString());
      throw e;
    }
  }

  private List<CalendarEventDto> mapEvents(Map<String, Object> response) {
    List<CalendarEventDto> events = new ArrayList<>();

    if (response == null) {
      return events;
    }

    List<Map<String, Object>> items = (List<Map<String, Object>>) response.get("items");
    if (items == null) {
      return events;
    }

    for (Map<String, Object> item : items) {
      String id = (String) item.get("id");
      String summary = (String) item.getOrDefault("summary", "(без названия)");

      Map<String, Object> startMap = (Map<String, Object>) item.get("start");
      Map<String, Object> endMap = (Map<String, Object>) item.get("end");

      String start = extractDateOrDateTime(startMap);
      String end = extractDateOrDateTime(endMap);

      events.add(new CalendarEventDto(id, summary, start, end));
    }

    return events;
  }

  private String extractDateOrDateTime(Map<String, Object> value) {
    if (value == null) {
      return null;
    }

    Object dateTime = value.get("dateTime");
    if (dateTime != null) {
      return dateTime.toString();
    }

    Object date = value.get("date");
    if (date != null) {
      return date.toString();
    }

    return null;
  }
}
