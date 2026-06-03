

// import com.alibaba.fastjson.JSON;
// import com.alibaba.fastjson.JSONObject;

// import javax.crypto.Mac;
// import javax.crypto.spec.SecretKeySpec;
// import java.io.InputStream;
// import java.io.OutputStream;
// import java.net.HttpURLConnection;
// import java.net.URL;
// import java.nio.charset.StandardCharsets;
// import java.security.MessageDigest;
// import java.util.*;
// import java.util.stream.Collectors;

// public class AIDZApiTest {

//     // ===== 配置区域 =====
//     private static final String BASE_URL = "https://appalpha1.tingyun.com/appops/rpc.po/deepzore/api/v1";
//     //    private static final String BASE_URL = "https://appalpha1.tingyun.com/appops/rpc.po/deepzore/api/v1";
//     //品友账号
//     private static final String API_KEY = "BBKdIpDDxn";
//     private static final String API_SECRET = "a3f8c2d1e4b7096f5a2c8e3d1f4b7096a3f8c2d1e4b7096f5a2c8e3d1f4b709";
//     //ceshi_my3账号
// //    private static final String API_KEY = "mcEjYjVkTJ";
// //    private static final String API_SECRET = "5e62ffbe3e460c46182570a91295cc7cc49e6a0902f8dd5d129bf35226c756ee";
//     // ====================

//     public static void main(String[] args) throws Exception {
//         String taskId = "0511";
//         String batchId = "001";
//         String question = "今天哪些股票涨得好？";
//         //跑多少个任务
// //        int repeatCount = 100;

// //        testLoadTasks("6418", 30);

// //        System.out.println("========== 1. createTask ==========");
// //        testCreateTask(taskId, batchId, question, repeatCount);

// //        System.out.println("\n========== 5. getTaskData ==========");
// //        testGetTaskData(taskId, batchId);

// //        System.out.println("\n========== 2. queryByTaskId ==========");
// //        testQueryByTaskId(taskId);

// //        System.out.println("\n========== 3. queryByTaskIdAndBatchId ==========");
// //        testQueryByTaskIdAndBatchId(taskId, batchId);

// //        System.out.println("\n========== 4. updateTask ==========");
// //        testUpdateTask(taskId);

// //        System.out.println("\n========== 4a. updateTask（含 batchId）==========");
// //        testUpdateTaskByBatch(taskId, batchId);

//         System.out.println("\n========== 6. listAllTasks（时间范围）==========");
//         String result = testListTasksByTimeRange(1779638400000L, 1779984000000L);
//         JSONObject json = JSONObject.parseObject(result);
//         List<JSONObject> tasks = json.getJSONArray("data").toJavaList(JSONObject.class);

//         // 按 askMethod 分组，统计任务数和 repeatCount 总和
//         Map<String, List<JSONObject>> byAskMethod = tasks.stream().collect(Collectors.groupingBy(t -> t.getString("askMethod")));

//         System.out.println("========== 按 askMethod 统计 ==========");
//         for (Map.Entry<String, List<JSONObject>> entry : byAskMethod.entrySet()) {
//             List<JSONObject> group = entry.getValue();
//             int taskCount = 0;
//             int repeatCount = 0;
//             int totalDataCount = 0;
//             for (JSONObject task : group) {
//                 String taskDataResult = testGetTaskData(task.getString("taskId"), task.getString("batchId"));
//                 JSONObject dataJson = JSONObject.parseObject(taskDataResult);
//                 int dataCount = 0;
//                 if (dataJson.getIntValue("code") == 0) {
//                     dataCount = dataJson.getJSONArray("data").toJavaList(JSONObject.class).stream().mapToInt(t -> t.getJSONArray("data").size()).sum();
//                 }
//                 System.out.printf("id=%s taskId=%s batchId=%s question=%s askMethod=%s repeatCount=%s dataCount=%s ctime=%s\n",
//                         task.getIntValue("id"),
//                         task.getString("taskId"),
//                         task.getString("batchId"),
//                         task.getString("question"),
//                         task.getString("askMethod"),
//                         task.getIntValue("repeatCount"),
//                         dataCount,
//                         task.getString("ctime"));
//                 if (dataCount > 0) {
//                     taskCount++;
//                     repeatCount += task.getIntValue("repeatCount");
//                     totalDataCount += dataCount;
//                 }

//             }
//             System.out.println();
//             System.out.println();
//             System.out.println();
//             System.out.printf("askMethod=%-12s 任务数=%d  repeatCount数=%d totalDataCount总数=%d%n", entry.getKey(), taskCount, repeatCount, totalDataCount);
//         }

// //        System.out.println("\n========== load tasks from f.csv ==========");
// //        testLoadTasks("src/test/java/com/tingyun/appops/thirdParty/f2.csv");

// //        System.out.println("\n========== 6a. listAllTasks 按状态过滤 ==========");
// //        testListTasksByStatus(0);
// //
// //        System.out.println("\n========== 6b. listAllTasks 按时间范围过滤 ==========");
// //        testListTasksByTimeRange(1778428800000L, 1778515200000L);
// //
// //        System.out.println("\n========== 6c. listAllTasks 状态+时间范围 ==========");
// //        testListTasksByStatusAndTimeRange(2, 1776787200000L, 1776816000000L);
// //        System.out.println("\n========== 6d. listAllTasks 非法状态（预期 400）==========");
// //        testListTasksByStatus("invalid_status");
// //
// //        System.out.println("\n========== 7. 签名错误（预期 401）==========");
// //        testInvalidSignature(taskId);
//     }

//     // ------------------------------------------------------------------ cases

//     static void testCreateTask(String taskId, String batchId, String question, int repeatCount) throws Exception {
//         JSONObject scope = new JSONObject();
//         scope.put("platform_group", new String[]{"doubao_app"});
//         scope.put("region", new String[]{});
//         scope.put("device_type", "ios");
//         scope.put("ask_method", "thinking");

//         JSONObject body = new JSONObject();
//         body.put("task_id", taskId);
//         body.put("batch_id", batchId);
//         body.put("question", question);
//         body.put("scope", scope);
//         body.put("repeat_count", repeatCount);
//         body.put("priority", 2);

//         String resp = send("POST", "/tasks/create", body.toJSONString(), null);
//         printResult(resp);
//     }

//     static void testQueryByTaskId(String taskId) throws Exception {
//         String resp = send("GET", "/tasks/" + taskId + "/status", "", null);
//         printResult(resp);
//     }

//     static void testQueryByTaskIdAndBatchId(String taskId, String batchId) throws Exception {
//         String query = "?task_id=" + taskId + "&batch_id=" + batchId;
//         String resp = send("GET", "/tasks/status" + query, "", null);
//         printResult(resp);
//     }

//     static void testUpdateTask(String taskId) throws Exception {
//         JSONObject body = new JSONObject();
//         body.put("status", "cancel");
//         body.put("priority", 0);
//         body.put("message", "测试取消");

//         String resp = send("PUT", "/tasks/" + taskId + "/update", body.toJSONString(), null);
//         printResult(resp);
//     }

//     /**
//      * 按 task_id + batch_id 联合修改任务
//      * PUT /tasks/{task_id}/{batch_id}/update
//      */
//     static void testUpdateTaskByBatch(String taskId, String batchId) throws Exception {
//         JSONObject body = new JSONObject();
//         body.put("status", "cancel");
//         body.put("priority", 0);
//         body.put("message", "测试按 batchId 取消");

//         String resp = send("PUT", "/tasks/" + taskId + "/" + batchId + "/update", body.toJSONString(), null);
//         printResult(resp);
//     }

//     static String testGetTaskData(String taskId, String batchId) throws Exception {
//         String query = "?batch_id=" + batchId;
//         String resp = send("GET", "/tasks/" + taskId + "/data" + query, "", null);
//         return printResult(resp);
//     }

//     static String testListAllTasks() throws Exception {
//         String resp = send("GET", "/tasks", "", null);
//         return printResult(resp);
//     }

//     /**
//      * 按状态过滤，status 取值：pending / in_progress / completed / failed / cancel
//      */
//     static void testListTasksByStatus(Integer status) throws Exception {
//         String resp = send("GET", "/tasks?status=" + status, "", null);
//         printResult(resp);
//     }

//     /**
//      * 按 ctime 时间范围过滤，startTime / endTime 为 Unix 秒级时间戳
//      */
//     static String testListTasksByTimeRange(long startTime, long endTime) throws Exception {
//         String query = "?start_time=" + startTime + "&end_time=" + endTime;
//         String resp = send("GET", "/tasks" + query, "", null);
//         return printResult(resp);
//     }

//     /**
//      * 同时按状态和时间范围过滤
//      */
//     static void testListTasksByStatusAndTimeRange(int status, long startTime, long endTime) throws Exception {
//         String query = "?status=" + status + "&start_time=" + startTime + "&end_time=" + endTime;
//         String resp = send("GET", "/tasks" + query, "", null);
//         printResult(resp);
//     }

//     /**
//      * 故意传错签名，验证服务端返回 401
//      */
//     static void testInvalidSignature(String taskId) throws Exception {
//         String resp = send("GET", "/tasks/" + taskId + "/status", "", "invalid_signature_xyz");
//         printResult(resp);
//     }

//     /**
//      * 读取 CSV，统计每个 taskId 的出现次数，依次 POST 到 load 接口
//      */
//     static void testLoadTasks(String taskId, int count) throws Exception {
//         String loadBase = "https://wkat1.tingyun.com/apptasksvr/aidz-manager/load";
//         String urlStr = loadBase + "/" + taskId + "?repeatCount=" + count;
//         while (true) {
//             System.out.println("  POST " + urlStr);
//             HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
//             conn.setRequestMethod("POST");
//             conn.setConnectTimeout(5000);
//             conn.setReadTimeout(10000);
//             conn.setDoOutput(true);
//             conn.getOutputStream().close();
//             int httpStatus = conn.getResponseCode();
//             InputStream is = httpStatus >= 400 ? conn.getErrorStream() : conn.getInputStream();
//             String resp = is == null ? "" : new String(is.readAllBytes(), StandardCharsets.UTF_8);
//             System.out.println("  HTTP " + httpStatus + " -> " + resp);
//             boolean success = false;
//             try {
//                 Object parsed = JSON.parse(resp);
//                 if (parsed instanceof JSONObject) {
//                     success = Boolean.TRUE.equals(((JSONObject) parsed).getBoolean("success"));
//                 }
//             } catch (Exception ignored) {
//             }
//             if (success) break;
//             System.out.println("  load failed, retrying in 10s...");
//             Thread.sleep(30_000);

//         }
//         System.out.println("end");
//     }

//     // ------------------------------------------------------------------ utils

//     /**
//      * 发送带签名头的 HTTP 请求
//      *
//      * @param method            GET / POST / PUT
//      * @param path              相对路径，含前导 /（如 /tasks/create）
//      * @param bodyJson          请求体 JSON 字符串，GET 时传 ""
//      * @param overrideSignature 非 null 时使用此值替换正确签名（用于测试签名失败）
//      */
//     static String send(String method, String path, String bodyJson, String overrideSignature) throws Exception {
//         // 路径部分（不含 query）用于签名
//         String signPath = BASE_URL.replaceFirst("https?://[^/]+", "") + path;
//         int queryIdx = signPath.indexOf('?');
//         if (queryIdx > 0) signPath = signPath.substring(0, queryIdx);

//         String timestamp = String.valueOf(System.currentTimeMillis() / 1000L);
//         String nonce = UUID.randomUUID().toString();
//         byte[] bodyBytes = bodyJson.getBytes(StandardCharsets.UTF_8);
//         String bodySha256 = sha256Hex(bodyBytes);

//         String stringToSign = method.toUpperCase() + "\n"
//                 + signPath + "\n"
//                 + timestamp + "\n"
//                 + nonce + "\n"
//                 + bodySha256;

//         String signature = overrideSignature != null
//                 ? overrideSignature
//                 : hmacSha256Hex(API_SECRET, stringToSign);
//         String url = BASE_URL + path;
// //
// //        System.out.println("  url : " + url);
// //        System.out.println("  stringToSign : " + stringToSign.replace("\n", "\\n"));
// //        System.out.println("  signature    : " + signature);

//         HttpURLConnection conn = (HttpURLConnection) new URL(BASE_URL + path).openConnection();
//         conn.setRequestMethod(method);
//         conn.setConnectTimeout(5000);
//         conn.setReadTimeout(10000);
//         conn.setRequestProperty("Content-Type", "application/json;charset=UTF-8");
//         conn.setRequestProperty("X-Api-Key", API_KEY);
//         conn.setRequestProperty("X-Api-Timestamp", timestamp);
//         conn.setRequestProperty("X-Api-Nonce", nonce);
//         conn.setRequestProperty("X-Api-Signature", signature);

//         if (!"GET".equalsIgnoreCase(method) && bodyBytes.length > 0) {
//             conn.setDoOutput(true);
//             try (OutputStream os = conn.getOutputStream()) {
//                 os.write(bodyBytes);
//             }
//         }

//         int status = conn.getResponseCode();
//         InputStream is = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
//         String responseBody = is == null ? "" : new String(is.readAllBytes(), StandardCharsets.UTF_8);
// //        System.out.println("  HTTP " + status);
//         return responseBody;
//     }

//     static String printResult(String body) {
//         try {
// //            System.out.println("  Response: \n" + JSON.toJSONString(JSON.parse(body), true));
//             return JSON.toJSONString(JSON.parse(body));
//         } catch (Exception e) {
//             System.out.println("  Response: " + body);
//             return null;
//         }
//     }

//     static String sha256Hex(byte[] data) throws Exception {
//         MessageDigest digest = MessageDigest.getInstance("SHA-256");
//         return bytesToHex(digest.digest(data));
//     }

//     static String hmacSha256Hex(String secret, String data) throws Exception {
//         Mac mac = Mac.getInstance("HmacSHA256");
//         mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
//         return bytesToHex(mac.doFinal(data.getBytes(StandardCharsets.UTF_8)));
//     }

//     static String bytesToHex(byte[] bytes) {
//         StringBuilder sb = new StringBuilder(bytes.length * 2);
//         for (byte b : bytes) sb.append(String.format("%02x", b));
//         return sb.toString();
//     }
// }
