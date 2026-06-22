# CareWave FastAPI API 명세서

Base URL: `http://<서버IP>:8000`

---

## REST API

---

### 1. 서버 상태 확인

| 항목 | 내용 |
|---|---|
| **이름** | 서버 헬스체크 |
| **Method** | GET |
| **Path** | `/` |

**Request**
없음

**Response** `200 OK`
```json
{
  "message": "CareWave FastAPI Server"
}
```

---

### 2. 하드웨어 연결 상태

| 항목 | 내용 |
|---|---|
| **이름** | 하드웨어 연결 상태 조회 |
| **Method** | GET |
| **Path** | `/api/status` |

**Request**
없음

**Response** `200 OK`
```json
{
  "hardware_connected": true
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `hardware_connected` | boolean | ESP32 UDP 수신 여부 |

---

### 3. 재실/공실 상태 조회

| 항목 | 내용 |
|---|---|
| **이름** | 재실 상태 조회 |
| **Method** | GET |
| **Path** | `/api/presence` |

**Request**
없음

**Response** `200 OK`
```json
{
  "status": "재실",
  "detected_at": "2026-06-01T14:30:00.123+09:00"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `status` | string | `"재실"` 또는 `"공실"` |
| `detected_at` | string (ISO 8601, KST) | 마지막 감지 시각 |

---

### 4. 마지막 낙상 이벤트 조회

| 항목 | 내용 |
|---|---|
| **이름** | 낙상 이벤트 조회 |
| **Method** | GET |
| **Path** | `/api/fall` |

**Request**
없음

**Response** `200 OK` — 이벤트 있을 때
```json
{
  "event_type": "낙상 감지",
  "occurred_at": "2026-06-01T14:30:00.123+09:00",
  "status": "미확인"
}
```

**Response** `200 OK` — 이벤트 없을 때
```json
{
  "event_type": null,
  "occurred_at": null
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `event_type` | string \| null | `"낙상 감지"` 또는 null |
| `occurred_at` | string (ISO 8601, KST) \| null | 낙상 발생 시각 |
| `status` | string | `"미확인"` |

---

## WebSocket API

---

### 5. 재실/공실 실시간 수신

| 항목 | 내용 |
|---|---|
| **이름** | 재실 상태 실시간 스트림 |
| **Protocol** | WebSocket |
| **Path** | `/ws/presence` |

**연결**
```
ws://<서버IP>:8000/ws/presence
```

**Request** (클라이언트 → 서버)
없음 (연결 유지만 하면 됨)

**Response** (서버 → 클라이언트, 상태 변경 시마다 push)
```json
{
  "status": "재실",
  "confidence": 0.9231,
  "rx": "RX1",
  "detected_at": "2026-06-01T14:30:00.123+09:00"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `status` | string | `"재실"` 또는 `"공실"` |
| `confidence` | float (0~1) | ML 모델 신뢰도 |
| `rx` | string | 수신 안테나 (`RX1` / `RX2` / `RX3`) |
| `detected_at` | string (ISO 8601, KST) | 감지 시각 |

---

### 6. 낙상 이벤트 실시간 수신

| 항목 | 내용 |
|---|---|
| **이름** | 낙상 이벤트 실시간 스트림 |
| **Protocol** | WebSocket |
| **Path** | `/ws/fall` |

**연결**
```
ws://<서버IP>:8000/ws/fall
```

**Request** (클라이언트 → 서버)
없음 (연결 유지만 하면 됨)

**Response** (서버 → 클라이언트, 낙상 감지 시 push)
```json
{
  "event_type": "낙상 감지",
  "occurred_at": "2026-06-01T14:30:00.123+09:00",
  "status": "미확인"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `event_type` | string | 항상 `"낙상 감지"` |
| `occurred_at` | string (ISO 8601, KST) | 낙상 발생 시각 |
| `status` | string | 항상 `"미확인"` |

---

### 7. CSI 실시간 스트림 (그래프용)

| 항목 | 내용 |
|---|---|
| **이름** | CSI 데이터 실시간 스트림 |
| **Protocol** | WebSocket |
| **Path** | `/ws/csi` |

**연결**
```
ws://<서버IP>:8000/ws/csi
```

**Request** (클라이언트 → 서버)
없음 (연결 유지만 하면 됨)

**Response** (서버 → 클라이언트, UDP 패킷 수신마다 push)
```json
{
  "timestamp": "2026-06-01T14:30:00.123+09:00",
  "rx": "RX1",
  "subcarriers": [45.2112, 38.1043, 52.7891, 41.3204, 49.8017],
  "amp_mean": 45.4453
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `timestamp` | string (ISO 8601, KST) | 수신 시각 |
| `rx` | string | 수신 안테나 (`RX1` / `RX2` / `RX3`) |
| `subcarriers` | float[] (5개) | 전체 서브캐리어 중 균등 샘플링한 amplitude |
| `amp_mean` | float | 전체 서브캐리어 amplitude 평균 |

> 수신 빈도: ESP32 전송 주기와 동일 (약 10~20Hz)

---

## Spring Boot 연동

FastAPI가 낙상 감지 시 Spring Boot로 자동 HTTP POST 전송

| 항목 | 내용 |
|---|---|
| **이름** | 낙상 이벤트 전송 |
| **Method** | POST |
| **Path** | `${SPRINGBOOT_URL}/api/events` |

**Request Body**
```json
{
  "event_type": "낙상 감지",
  "occurred_at": "2026-06-01T14:30:00.123+09:00",
  "status": "미확인"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `event_type` | string | 항상 `"낙상 감지"` |
| `occurred_at` | string (ISO 8601, KST) | 낙상 발생 시각 |
| `status` | string | 항상 `"미확인"` |
