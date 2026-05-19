package personal.jarvis_plan_my_day.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import personal.jarvis_plan_my_day.dto.CalendarEventDto;
import personal.jarvis_plan_my_day.dto.CalendarEventsResponseDto;

import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.List;

//TODO: add an endpoint with starting and ending dates
@Service
public class GoogleCalendarService {

  private static final Logger log = LoggerFactory.getLogger(GoogleCalendarService.class);

  private static final String PRIMARY_CALENDAR = "primary";
  private static final int PAGE_SIZE = 250;          // максимум для Calendar API
  private static final int MAX_PAGES = 50;           // safety cap: 12500 событий
  private static final int MAX_DAYS = 365 * 3;       // ограничение глубины запроса

  private final RestClient restClient;

  public GoogleCalendarService() {
    this.restClient = RestClient.builder()
            .baseUrl("https://www.googleapis.com/calendar/v3")
            .build();
  }

  // -------- Public API --------

  public List<CalendarEventDto> getTodayEvents(OAuth2AuthorizedClient authorizedClient) {
    ZoneId zoneId = ZoneId.systemDefault();
    ZonedDateTime startOfDay = ZonedDateTime.now(zoneId)
            .toLocalDate()
            .atStartOfDay(zoneId);
    ZonedDateTime endOfDay = startOfDay.plusDays(1);
    return getEventsBetween(authorizedClient, startOfDay, endOfDay);
  }

  public List<CalendarEventDto> getEventsForLastDays(
          OAuth2AuthorizedClient authorizedClient,
          int days
  ) {
    days = normalizeDays(days);
    ZoneId zoneId = ZoneId.systemDefault();
    ZonedDateTime now = ZonedDateTime.now(zoneId);
    ZonedDateTime startDateTime = now.minusDays(days);
    return getEventsBetween(authorizedClient, startDateTime, now);
  }

  // -------- Internal --------

  private List<CalendarEventDto> getEventsBetween(
          OAuth2AuthorizedClient authorizedClient,
          ZonedDateTime from,
          ZonedDateTime to
  ) {
    String accessToken = authorizedClient.getAccessToken().getTokenValue();
    String timeMin = from.toInstant().toString();
    String timeMax = to.toInstant().toString();

    List<CalendarEventDto> allEvents = new ArrayList<>();
    String pageToken = null;
    int pageCount = 0;

    do {
      final String currentToken = pageToken;
      try {
        CalendarEventsResponseDto response = restClient.get()
                .uri(uriBuilder -> {
                  uriBuilder.path("/calendars/{calendarId}/events")
                          .queryParam("timeMin", timeMin)
                          .queryParam("timeMax", timeMax)
                          .queryParam("singleEvents", "true")
                          .queryParam("orderBy", "startTime")
                          .queryParam("maxResults", PAGE_SIZE);
                  if (currentToken != null) {
                    uriBuilder.queryParam("pageToken", currentToken);
                  }
                  return uriBuilder.build(PRIMARY_CALENDAR);
                })
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
                .retrieve()
                .body(CalendarEventsResponseDto.class);

        if (response == null) {
          break;
        }
        if (response.items() != null) {
          allEvents.addAll(response.items());
        }
        pageToken = response.nextPageToken();
        pageCount++;

        if (pageCount >= MAX_PAGES) {
          log.warn("Reached page limit ({}) while fetching calendar events; " +
                          "got {} events, results may be incomplete",
                  MAX_PAGES, allEvents.size());
          break;
        }

      } catch (HttpClientErrorException e) {
        log.error("Google Calendar API error: status={}, body={}",
                e.getStatusCode(), e.getResponseBodyAsString());
        throw e;
      }
    } while (pageToken != null);

    log.info("Fetched {} events from {} to {} ({} pages)",
            allEvents.size(), timeMin, timeMax, pageCount);
    return allEvents;
  }

  private int normalizeDays(int days) {
    if (days < 1) return 1;
    if (days > MAX_DAYS) return MAX_DAYS;
    return days;
  }
}