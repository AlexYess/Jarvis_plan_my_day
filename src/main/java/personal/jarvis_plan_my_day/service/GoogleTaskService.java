package personal.jarvis_plan_my_day.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import personal.jarvis_plan_my_day.dto.TaskDto;
import personal.jarvis_plan_my_day.dto.TaskListDto;
import personal.jarvis_plan_my_day.dto.TaskListsResponseDto;
import personal.jarvis_plan_my_day.dto.TasksResponseDto;

import java.util.ArrayList;
import java.util.List;

@Service
public class GoogleTaskService {

  private static final Logger log = LoggerFactory.getLogger(GoogleTaskService.class);
  private static final String TODO_LIST_NAME = "To Do List";
  private static final int PAGE_SIZE = 100;  // max для Tasks API (для Calendar - 250)

  private final RestClient restClient;

  public GoogleTaskService() {
    this.restClient = RestClient.builder()
            .baseUrl("https://tasks.googleapis.com/tasks/v1")
            .build();
  }

  // -------- Public API --------

  public List<TaskDto> getTasks(OAuth2AuthorizedClient authorizedClient) {
    String accessToken = authorizedClient.getAccessToken().getTokenValue();
    String toDoListId = findTaskListIdByTitle(accessToken, TODO_LIST_NAME);
    return fetchAllTasks(accessToken, toDoListId);
  }

  public List<TaskListDto> getTaskLists(OAuth2AuthorizedClient authorizedClient) {
    return fetchAllTaskLists(authorizedClient.getAccessToken().getTokenValue());
  }

  // -------- Internal --------

  private String findTaskListIdByTitle(String accessToken, String title) {
    return fetchAllTaskLists(accessToken).stream()
            .peek(tl -> log.debug("Task list: {} id={}", tl.title(), tl.id()))
            .filter(tl -> title.equals(tl.title()))
            .map(TaskListDto::id)
            .findFirst()
            .orElseThrow(() -> new IllegalStateException(
                    "Task list '" + title + "' not found"));
  }

  private List<TaskListDto> fetchAllTaskLists(String accessToken) {
    List<TaskListDto> all = new ArrayList<>();
    String pageToken = null;

    do {
      final String currentToken = pageToken;
      try {
        TaskListsResponseDto response = restClient.get()
                .uri(uriBuilder -> {
                  uriBuilder.path("/users/@me/lists");
                  if (currentToken != null) {
                    uriBuilder.queryParam("pageToken", currentToken);
                  }
                  return uriBuilder.build();
                })
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
                .retrieve()
                .body(TaskListsResponseDto.class);

        if (response != null && response.items() != null) {
          all.addAll(response.items());
        }
        pageToken = response != null ? response.nextPageToken() : null;

      } catch (HttpClientErrorException e) {
        log.error("Google Tasks API error fetching task lists: status={}, body={}",
                e.getStatusCode(), e.getResponseBodyAsString());
        throw e;
      }
    } while (pageToken != null);

    log.info("Fetched {} task lists", all.size());
    return all;
  }

  private List<TaskDto> fetchAllTasks(String accessToken, String taskListId) {
    List<TaskDto> all = new ArrayList<>();
    String pageToken = null;

    do {
      final String currentToken = pageToken;
      try {
        TasksResponseDto response = restClient.get()
                .uri(uriBuilder -> {
                  uriBuilder.path("/lists/{tasklist}/tasks")
                          .queryParam("maxResults", PAGE_SIZE)
                          .queryParam("showCompleted", true)
                          .queryParam("showHidden", true);
                  if (currentToken != null) {
                    uriBuilder.queryParam("pageToken", currentToken);
                  }
                  return uriBuilder.build(taskListId);
                })
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
                .retrieve()
                .body(TasksResponseDto.class);

        if (response != null && response.items() != null) {
          all.addAll(response.items());
        }
        pageToken = response != null ? response.nextPageToken() : null;

      } catch (HttpClientErrorException e) {
        log.error("Google Tasks API error fetching tasks: status={}, body={}",
                e.getStatusCode(), e.getResponseBodyAsString());
        throw e;
      }
    } while (pageToken != null);

    log.info("Fetched {} tasks from list {}", all.size(), taskListId);
    return all;
  }
}