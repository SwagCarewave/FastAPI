# CareWave FastAPI 서버 API 명세서

Base URL: `http://<서버IP>:8000`

---

## REST API

### GET `/`
서버 헬스체크

**Response**
```json
{ "message": "CareWave FastAPI Server" }
```

---

### GET `/api/status`
하드웨어(ESP32) 연결 상태 확인

**Response**
```json
{ "hardware_connected": true }
```

---

### GET `/api/presence`
현재 재실/공실 상태 조회

**Response**
```json
{
  "status": "재실",
  "detected_at": "2026-06-01T14:30:00.123+09:00"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `status` | string | `"재실"` 또는 `"공실"` |
| `detected_at` | string (ISO 8601) | 마지막 감지 시각 (KST) |

---

### GET `/api/fall`
마지막 낙상 이벤트 조회

**Response (이벤트 있을 때)**
```json
{
  "event_type": "낙상 감지",
  "occurred_at": "2026-06-01T14:30:00.123+09:00",
  "status": "미확인"
}
```

**Response (이벤트 없을 때)**
```json
{ "event_type": null, "occurred_at": null }
```

---

## WebSocket API

### WS `/ws/presence`
재실/공실 상태 실시간 수신

**연결 방법**
```
ws://<서버IP>:8000/ws/presence
```

**수신 메시지 (상태 변경 시마다 push)**
```json
{
  "status":      "재실",
  "confidence":  0.9231,
  "rx":          "RX1",
  "detected_at": "2026-06-01T14:30:00.123+09:00"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `status` | string | `"재실"` 또는 `"공실"` |
| `confidence` | float (0~1) | ML 모델 신뢰도 |
| `rx` | string | 수신 안테나 (`RX1` / `RX2` / `RX3`) |
| `detected_at` | string (ISO 8601) | 감지 시각 (KST) |

---

### WS `/ws/fall`
낙상 이벤트 실시간 수신

**연결 방법**
```
ws://<서버IP>:8000/ws/fall
```

**수신 메시지 (낙상 감지 시 push)**
```json
{
  "event_type": "낙상 감지",
  "occurred_at": "2026-06-01T14:30:00.123+09:00",
  "status":     "미확인"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `event_type` | string | 항상 `"낙상 감지"` |
| `occurred_at` | string (ISO 8601) | 낙상 발생 시각 (KST) |
| `status` | string | 항상 `"미확인"` (Spring Boot에서 확인 후 변경) |

> Spring Boot로도 동시에 HTTP POST `/api/events`가 전송됩니다.

---

### WS `/ws/csi`
CSI 원시 데이터 실시간 수신 (그래프용)

**연결 방법**
```
ws://<서버IP>:8000/ws/csi
```

**수신 메시지 (UDP 패킷 수신마다 push)**
```json
{
  "timestamp":   "2026-06-01T14:30:00.123+09:00",
  "rx":          "RX1",
  "subcarriers": [45.2112, 38.1043, 52.7891, 41.3204, 49.8017],
  "amp_mean":    45.4453
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `timestamp` | string (ISO 8601) | 수신 시각 (KST) |
| `rx` | string | 수신 안테나 (`RX1` / `RX2` / `RX3`) |
| `subcarriers` | float[] (5개) | 전체 서브캐리어 중 균등 샘플링한 5개 amplitude |
| `amp_mean` | float | 전체 서브캐리어 amplitude 평균 |

**프론트엔드 그래프 구현 예시**
- X축: `timestamp`
- Y축: `subcarriers[0]` ~ `subcarriers[4]` 각각을 별도 선으로 표시
- 범례: `Subcarrier 1` ~ `Subcarrier 5` (또는 `RX1 SC1` 등으로 안테나 구분)
- `amp_mean`을 별도 선으로 추가하면 전체 신호 세기 추세 확인 가능

> 수신 빈도는 ESP32 전송 주기와 동일 (보통 10~20Hz).
> 프론트에서 버퍼 크기를 제한(예: 최근 200포인트)하여 메모리 관리 권장.

---

## Spring Boot 연동 (FastAPI → Spring Boot)

### POST `${SPRINGBOOT_URL}/api/events`
낙상 감지 시 FastAPI가 자동으로 호출

**Request Body**
```json
{
  "event_type": "낙상 감지",
  "occurred_at": "2026-06-01T14:30:00.123+09:00",
  "status":     "미확인"
}
```
