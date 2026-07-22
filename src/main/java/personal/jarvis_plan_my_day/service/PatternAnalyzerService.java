package personal.jarvis_plan_my_day.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import personal.jarvis_plan_my_day.dto.CalendarEventDto;
import personal.jarvis_plan_my_day.dto.ClassifyTasksRequestDto;
import personal.jarvis_plan_my_day.dto.PatternAnalysisRequestDto;
import personal.jarvis_plan_my_day.dto.TaskDto;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
public class PatternAnalyzerService {

    private final ObjectMapper objectMapper;

    public PatternAnalyzerService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Value("${python.analyzer.url}")
    private String analyzerBaseUrl;

    public Map<String, Object> analyzeEvents(Long userId, List<CalendarEventDto> events) {
        try {
            PatternAnalysisRequestDto requestDto =
                    new PatternAnalysisRequestDto(userId, events);

            String jsonBody = objectMapper.writeValueAsString(requestDto);

            log.info("Sending request to Python analyzer");
            log.info("Events count: {}", events.size());
            log.info("JSON body length: {}", jsonBody.length());

            HttpClient httpClient = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(10))
                    .build();

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("http://localhost:8000/analyze"))
                    .version(HttpClient.Version.HTTP_1_1)
                    .timeout(Duration.ofMinutes(3))
                    .header("Content-Type", "application/json; charset=utf-8")
                    .header("Accept", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(jsonBody, StandardCharsets.UTF_8))
                    .build();

            HttpResponse<String> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
            );

            log.info("Python analyzer response status: {}", response.statusCode());
            log.info("Python analyzer response body: {}", response.body());

            if (response.statusCode() >= 400) {
                throw new IllegalStateException(
                        "Pattern analyzer returned error. Status: "
                                + response.statusCode()
                                + ", body: "
                                + response.body()
                );
            }

            return objectMapper.readValue(
                    response.body(),
                    new TypeReference<Map<String, Object>>() {}
            );

        } catch (Exception e) {
            throw new IllegalStateException("Failed to call pattern analyzer service", e);
        }
    }

    public Map<String, Object> classifyTasks(Long userId, List<TaskDto> tasks) {
        try {
            ClassifyTasksRequestDto requestDto = new ClassifyTasksRequestDto(tasks, false);
            String jsonBody = objectMapper.writeValueAsString(requestDto);

            log.info("Sending {} tasks to Python classifier", tasks.size());
            log.info("JSON body length: {}", jsonBody.length());

            HttpClient httpClient = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(10))
                    .build();

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(analyzerBaseUrl + "/classify/tasks"))
                    .version(HttpClient.Version.HTTP_1_1)
                    .timeout(Duration.ofMinutes(3))
                    .header("Content-Type", "application/json; charset=utf-8")
                    .header("Accept", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(jsonBody, StandardCharsets.UTF_8))
                    .build();

            HttpResponse<String> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
            );

            log.info("Python classifier response status: {}", response.statusCode());

            if (response.statusCode() >= 400) {
                throw new IllegalStateException(
                        "Task classifier returned error. Status: "
                                + response.statusCode()
                                + ", body: "
                                + response.body()
                );
            }

            return objectMapper.readValue(
                    response.body(),
                    new TypeReference<Map<String, Object>>() {}
            );

        } catch (Exception e) {
            throw new IllegalStateException("Failed to call task classifier service", e);
        }
    }
}