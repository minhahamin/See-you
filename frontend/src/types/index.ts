// 백엔드 Pydantic 스키마(backend/api/schemas.py)와 같은 구조로 유지한다. 한쪽을 바꾸면 같이 수정할 것.

export type Category = 'sight' | 'food' | 'cafe' | 'stay' | 'activity';
export type AuthorType = '가족' | '커플' | '혼자' | '친구';
export type WeatherCondition = 'sunny' | 'cloudy' | 'rain';
/** 하루 중 방문의 역할. 일정 재배치에 쓰이며 화면에는 쓰지 않는다 */
export type Slot = 'morning' | 'lunch' | 'afternoon' | 'cafe' | 'dinner' | 'stay';

export interface Place {
  id: string;
  name: string;
  category: Category;
  address: string;
  lat: number;
  lng: number;
  description: string;
  thumbnail_url: string | null;
  indoor: boolean;
  tags: string[];
  checklist: string[];
}

export interface Review {
  review_id: string;
  place_id: string;
  text: string;
  rating: number;
  author_type: AuthorType;
  season: string;
  visit_time: string;
}

export interface Weather {
  condition: WeatherCondition;
  temp_max: number;
  temp_min: number;
}

export interface Visit {
  place_id: string;
  /** "HH:MM" */
  start: string;
  /** "HH:MM" */
  end: string;
  /** 직전 장소에서 이동하는 데 걸리는 시간(분). 하루 첫 방문은 0 */
  travel_minutes_from_prev: number;
  reason: string;
  evidence_review_ids: string[];
  /** 피드백으로 바뀐 블록 */
  changed: boolean;
  slot?: Slot | null;
}

export interface DayPlan {
  day: number;
  /** "YYYY-MM-DD" */
  date: string;
  /** 날씨를 가져올 수 없으면 null */
  weather: Weather | null;
  visits: Visit[];
}

export interface Validation {
  passed: number;
  total: number;
}

export interface Itinerary {
  title: string;
  region: string;
  companions: string;
  days: DayPlan[];
  validation: Validation;
}

/** 타임라인에서 선택한 방문: 일차 + 그날의 순번 */
export interface Selection {
  day: number;
  index: number;
}

// ---- 에이전트 대화 ----

export type ChatRole = 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
}

export type StepStatus = 'pending' | 'running' | 'done';

/** SSE `step` 이벤트에 대응: 노드 하나의 진행 상황 */
export interface AgentStep {
  node: string;
  label: string;
  status: StepStatus;
  duration_ms: number | null;
  /** 이 단계에서 쓴 LLM 토큰 수 (없으면 생략) */
  tokens?: number | null;
}

// ---- 사용자 설정 (동행·취향) ----

export type Companion = '혼자' | '커플' | '친구' | '가족';
export type BudgetLevel = 1 | 2 | 3;

export interface UserSettings {
  companion: Companion | null;
  preferences: string[];
  budget: BudgetLevel | null;
}

// ---- 성능 대시보드: /api/metrics/* 응답 형태. null = 데이터 없음 ----

export type MetricKey = 'recall_at_5' | 'mrr' | 'faithfulness' | 'violation_rate';

export interface ExperimentResult {
  version: string;
  description: string;
  recall_at_5: number | null;
  mrr: number | null;
  faithfulness: number | null;
  violation_rate: number | null;
}

export interface NodeMetric {
  node: string;
  avg_latency_ms: number | null;
  avg_tokens: number | null;
}

export interface RecentRun {
  run_id: string;
  response_sec: number;
  /** 토큰 단가가 설정되지 않으면 null */
  cost_usd: number | null;
}

export interface FailureReason {
  reason: string;
  count: number;
}

export interface RunMetrics {
  avg_response_sec: number | null;
  avg_cost_usd: number | null;
  recent: RecentRun[];
  regen_rate: number | null;
  top_failures: FailureReason[];
}

export interface MetricsSnapshot {
  experiments: ExperimentResult[];
  nodes: NodeMetric[];
  runs: RunMetrics | null;
  /** 데이터 출처 (예: eval/results/2026-xx-xx.csv). 없으면 null */
  sources: { experiments: string | null; nodes: string | null; runs: string | null };
  /** 화면 개발용 샘플이면 true */
  is_sample: boolean;
}

// ---- API 응답: backend/api/schemas.py와 같은 구조 ----

export interface PlaceDetail {
  place: Place;
  reviews: Review[];
  /** "후기는 합성 데이터입니다." */
  disclaimer: string;
}

/** SSE `step` 이벤트 */
export interface StepEvent {
  node: string;
  label: string;
  status: 'running' | 'done';
  duration_ms: number | null;
  tokens: number | null;
}

/** SSE `question` 이벤트 */
export interface QuestionEvent {
  question: string;
  missing_fields: string[];
}

/** SSE `itinerary` 이벤트: 일정에 등장하는 장소 목록을 함께 준다 */
export interface ItineraryEvent {
  itinerary: Itinerary;
  places: Place[];
  /** 검증을 통과하지 못한 항목 설명 */
  issues: string[];
}

/** SSE `error` 이벤트 */
export interface ErrorEvent {
  message: string;
}

export interface SessionSummary {
  session_id: string;
  messages: ChatMessage[];
  itinerary: Itinerary | null;
  places: Place[];
  /** 사용자 응답을 기다리는 중이면 어떤 응답인지 */
  awaiting: 'question' | 'feedback' | null;
}

export interface ExperimentsResponse {
  experiments: ExperimentResult[];
  source: string | null;
}

export interface RunsResponse {
  nodes: NodeMetric[];
  runs: RunMetrics | null;
  source: string | null;
}
