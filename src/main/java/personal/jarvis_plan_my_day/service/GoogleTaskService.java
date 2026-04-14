package personal.jarvis_plan_my_day.service;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import personal.jarvis_plan_my_day.dto.TaskDto;
import personal.jarvis_plan_my_day.dto.TaskListDto;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Service
public class GoogleTaskService {
  public final RestClient restClient;

  public GoogleTaskService() {
    this.restClient = RestClient.builder().baseUrl("https://tasks.googleapis.com/tasks/v1").build();
  }

  public List<TaskDto> getTasks(OAuth2AuthorizedClient authorizedClient) {
    String accessToken = authorizedClient.getAccessToken().getTokenValue();
    List<TaskListDto> taskLists = getTaskLists(authorizedClient);
    String toDoListID = null;
    for (TaskListDto taskListDto : taskLists) {
      System.out.println("Task list: " + taskListDto.title() + " id=" + taskListDto.id());
      if (taskListDto.title().equals("To Do List")) {
        toDoListID = taskListDto.id();
        break;
      }
    }
    if (toDoListID == null) {
      throw new IllegalStateException("Task list 'To Do List' not found");
    }
    try {
      Map<String, Object> response =
          restClient
              .get()
              .uri("/lists/{tasklist}/tasks", toDoListID)
              .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
              .retrieve()
              .body(Map.class);
      return mapTasks(response);
    } catch (HttpClientErrorException e) {
      System.out.println("Google Tasks API error: " + e.getStatusCode());
      System.out.println("Response body: " + e.getResponseBodyAsString());
      throw e;
    }
  }

  private List<TaskDto> mapTasks(Map<String, Object> response) {
    List<TaskDto> tasks = new ArrayList<>();
    if (response == null) return tasks;

    List<Map<String, Object>> items = (List<Map<String, Object>>) response.get("items");
    for (Map<String, Object> item : items) {
      String id = item.get("id").toString();
      String title = item.get("title").toString();
        String due = null;
        Object dueValue = item.get("due");
        if (dueValue != null) {
            due = dueValue.toString();
        }

        String completed = null;
        Object completedValue = item.get("completed");
        if (completedValue != null) {
            completed = completedValue.toString();
        }
        //TODO add notes field. Check for null

      tasks.add(new TaskDto(id, title, due, completed));
    }
    return tasks;
  }

  public List<TaskListDto> getTaskLists(OAuth2AuthorizedClient authorizedClient) {
    String accessToken = authorizedClient.getAccessToken().getTokenValue();

    try {
      Map<String, Object> response =
          restClient
              .get()
              .uri(uriBuilder -> uriBuilder.path("/users/@me/lists").build())
              .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
              .retrieve()
              .body(Map.class);
      return mapTaskLists(response);
    } catch (HttpClientErrorException e) {
      System.out.println("Google Tasks API error: " + e.getStatusCode());
      System.out.println("Response body: " + e.getResponseBodyAsString());
      throw e;
    }
  }

  private List<TaskListDto> mapTaskLists(Map<String, Object> response) {
    List<TaskListDto> taskLists = new ArrayList<>();
    if (response == null) {
      return taskLists;
    }
    List<Map<String, Object>> items = (List<Map<String, Object>>) response.get("items");
    for (Map<String, Object> item : items) {
      String id = item.get("id").toString();
      String title = item.get("title").toString();

      taskLists.add(new TaskListDto(id, title));
    }
    return taskLists;
  }
}
