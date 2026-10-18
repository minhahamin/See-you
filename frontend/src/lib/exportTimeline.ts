import { ArrowRight, Car } from 'lucide-react';
import type { DayPlan, Itinerary, Place, Visit } from '../types';
import { loadIcon } from './canvasIcons';
import { CATEGORY_META } from './category';
import { DAY_END_MIN, DAY_START_MIN, formatDate, toMinutes } from './time';
import { WEATHER_META } from './weather';

// 화면(타임라인)과 달리 저장용 이미지는 글씨가 잘 보이도록 시간축을 더 넓게 그린다.
const SCALE = 2; // 선명하게 보이도록 2배 해상도로 그린다
const FONT = '"Pretendard Variable", Pretendard, system-ui, sans-serif';
const PX_PER_HOUR = 160;
const TRACK_W = ((DAY_END_MIN - DAY_START_MIN) / 60) * PX_PER_HOUR;
const MARGIN = 24;
const PAD = 32;
const HEADER_H = 96;
const AXIS_H = 32;
const ROW_H = 112;
const ROW_GAP = 12;
const ROW_HEADER_W = 168;
const FOOTER_H = 44;
const PILL_H = 56;
const NARROW_W = 180; // 이보다 좁은 블록은 썸네일을 빼고 글씨를 넓게 쓴다
const ARROW_MIN_W = 220;

const WIDTH = (MARGIN + PAD) * 2 + ROW_HEADER_W + TRACK_W;

const C = {
  main: '#1F2937',
  sub: '#7B8494',
  row: '#FFF8FB',
  rain: '#E8F2FF',
  grid: 'rgba(238,123,166,0.16)',
};

const px = (minutes: number): number => ((minutes - DAY_START_MIN) / 60) * PX_PER_HOUR;

/** 너비를 넘으면 …으로 줄인다 */
function fit(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string {
  if (ctx.measureText(text).width <= maxWidth) return text;
  let t = text;
  while (t.length > 1 && ctx.measureText(`${t}…`).width > maxWidth) t = t.slice(0, -1);
  return `${t}…`;
}

function roundRectPath(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

/** 캔버스는 DOM의 글꼴을 자동으로 불러오지 않으므로, 쓸 글자가 있는 글꼴 조각을 미리 받는다 */
async function ensureFonts(itinerary: Itinerary, places: Record<string, Place>): Promise<void> {
  const text = [
    itinerary.title,
    itinerary.companions,
    '0123456789:°/.–·분일차 여행 일정 플래너',
    ...Object.values(places).map((p) => p.name),
  ].join('');
  try {
    await Promise.all(['400', '500', '700'].map((w) => document.fonts.load(`${w} 16px "Pretendard Variable"`, text)));
  } catch {
    // 글꼴을 못 받으면 기본 글꼴로 그린다
  }
}

async function drawVisit(
  ctx: CanvasRenderingContext2D, visit: Visit, place: Place, trackX: number, rowY: number,
): Promise<void> {
  const meta = CATEGORY_META[place.category];
  const left = trackX + px(toMinutes(visit.start));
  const width = px(toMinutes(visit.end)) - px(toMinutes(visit.start));
  const top = rowY + (ROW_H - PILL_H) / 2;
  const midY = top + PILL_H / 2;
  const narrow = width < NARROW_W;

  ctx.save();
  ctx.shadowColor = 'rgba(0,0,0,0.16)';
  ctx.shadowBlur = 24;
  ctx.shadowOffsetY = 8;
  ctx.fillStyle = meta.hex;
  roundRectPath(ctx, left, top, width, PILL_H, PILL_H / 2);
  ctx.fill();
  ctx.restore();

  let textX = left + 20;
  if (!narrow) {
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    ctx.beginPath();
    ctx.arc(left + 28, midY, 22, 0, Math.PI * 2);
    ctx.fill();
    ctx.drawImage(await loadIcon(meta.icon, meta.onHex, 22, SCALE), left + 17, midY - 11, 22, 22);
    textX = left + 60;
  }

  const hasArrow = width >= ARROW_MIN_W;
  const textMax = left + width - textX - (hasArrow ? 48 : 16);
  if (textMax > 24) {
    ctx.fillStyle = meta.onHex;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    ctx.font = `700 14px ${FONT}`;
    ctx.fillText(fit(ctx, place.name, textMax), textX, midY - 2);
    ctx.globalAlpha = 0.85;
    ctx.font = `400 11px ${FONT}`;
    ctx.fillText(`${visit.start}–${visit.end}`, textX, midY + 14);
    ctx.globalAlpha = 1;
  }

  if (hasArrow) {
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    ctx.beginPath();
    ctx.arc(left + width - 22, midY, 16, 0, Math.PI * 2);
    ctx.fill();
    ctx.drawImage(await loadIcon(ArrowRight, meta.onHex, 14, SCALE), left + width - 29, midY - 7, 14, 14);
  }
}

async function drawTravelGap(
  ctx: CanvasRenderingContext2D, prev: Visit, visit: Visit, trackX: number, rowY: number,
): Promise<void> {
  const gapLeft = trackX + px(toMinutes(prev.end));
  const gapWidth = px(toMinutes(visit.start)) - px(toMinutes(prev.end));
  if (gapWidth <= 0) return;

  const label = `${visit.travel_minutes_from_prev}분`;
  ctx.font = `500 11px ${FONT}`;
  const w = 8 + 12 + 4 + ctx.measureText(label).width + 10;
  const x = gapLeft + (gapWidth - w) / 2;
  const y = rowY + ROW_H / 2 - 11;

  ctx.fillStyle = 'rgba(255,255,255,0.9)';
  roundRectPath(ctx, x, y, w, 22, 11);
  ctx.fill();
  ctx.drawImage(await loadIcon(Car, C.sub, 12, SCALE), x + 8, y + 5, 12, 12);
  ctx.fillStyle = C.sub;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, x + 24, y + 11.5);
}

async function drawDay(
  ctx: CanvasRenderingContext2D, day: DayPlan, places: Record<string, Place>, x0: number, rowY: number,
): Promise<void> {
  const rowW = ROW_HEADER_W + TRACK_W;
  const trackX = x0 + ROW_HEADER_W;
  const forecast = day.weather;
  const weather = forecast ? WEATHER_META[forecast.condition] : null;

  // 행 배경 + 30분 단위 세로선
  ctx.save();
  roundRectPath(ctx, x0, rowY, rowW, ROW_H, 24);
  ctx.fillStyle = forecast?.condition === 'rain' ? C.rain : C.row;
  ctx.fill();
  ctx.clip();
  ctx.strokeStyle = C.grid;
  ctx.lineWidth = 1;
  for (let k = 0; k <= (TRACK_W / PX_PER_HOUR) * 2; k += 1) {
    const gx = trackX + (k * PX_PER_HOUR) / 2;
    ctx.beginPath();
    ctx.moveTo(gx, rowY);
    ctx.lineTo(gx, rowY + ROW_H);
    ctx.stroke();
  }
  ctx.restore();

  // 행 머리글: 일차, 날짜, 날씨
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = C.main;
  ctx.font = `700 20px ${FONT}`;
  ctx.fillText(`${day.day}일차`, x0 + 20, rowY + 40);
  ctx.fillStyle = C.sub;
  ctx.font = `400 12px ${FONT}`;
  ctx.fillText(formatDate(day.date), x0 + 20, rowY + 60);
  if (forecast && weather) {
    ctx.drawImage(await loadIcon(weather.icon, weather.hex, 14, SCALE), x0 + 20, rowY + 70, 14, 14);
    ctx.fillStyle = C.main;
    ctx.font = `500 12px ${FONT}`;
    ctx.fillText(`${forecast.temp_max}° / ${forecast.temp_min}°`, x0 + 40, rowY + 82);
  } else {
    ctx.fillStyle = C.sub;
    ctx.font = `400 12px ${FONT}`;
    ctx.fillText('날씨 정보 없음', x0 + 20, rowY + 82);
  }

  for (let i = 0; i < day.visits.length; i += 1) {
    const visit = day.visits[i];
    const place = places[visit.place_id];
    if (!place) continue;
    if (i > 0) await drawTravelGap(ctx, day.visits[i - 1], visit, trackX, rowY);
    await drawVisit(ctx, visit, place, trackX, rowY);
  }
}

/** 일정 전체 타임라인을 PNG 이미지로 그린다 (가로로 스크롤되는 부분도 모두 포함) */
export async function renderTimelineImage(itinerary: Itinerary, places: Record<string, Place>): Promise<Blob> {
  const dayCount = itinerary.days.length;
  const height =
    (MARGIN + PAD) * 2 + HEADER_H + AXIS_H + dayCount * ROW_H + Math.max(0, dayCount - 1) * ROW_GAP + FOOTER_H;

  await ensureFonts(itinerary, places);

  const canvas = document.createElement('canvas');
  canvas.width = WIDTH * SCALE;
  canvas.height = height * SCALE;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('canvas 2d context unavailable');
  ctx.scale(SCALE, SCALE);

  // 배경과 바깥 카드
  const bg = ctx.createLinearGradient(0, 0, WIDTH, height);
  bg.addColorStop(0, '#FFE1EB');
  bg.addColorStop(0.5, '#FFF1F5');
  bg.addColorStop(1, '#FFF9FB');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, WIDTH, height);
  ctx.fillStyle = 'rgba(255,255,255,0.6)';
  roundRectPath(ctx, MARGIN, MARGIN, WIDTH - MARGIN * 2, height - MARGIN * 2, 32);
  ctx.fill();

  const x0 = MARGIN + PAD;
  const y0 = MARGIN + PAD;
  const first = itinerary.days[0];
  const last = itinerary.days[dayCount - 1];

  // 제목
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = C.main;
  ctx.font = `700 30px ${FONT}`;
  ctx.fillText(itinerary.title, x0, y0 + 32);
  ctx.fillStyle = C.sub;
  ctx.font = `400 15px ${FONT}`;
  if (first && last) {
    ctx.fillText(`${formatDate(first.date)} – ${formatDate(last.date)} · ${itinerary.companions}`, x0, y0 + 60);
  }

  // 시간축
  const axisY = y0 + HEADER_H;
  ctx.font = `500 12px ${FONT}`;
  ctx.fillStyle = C.sub;
  for (let h = DAY_START_MIN / 60; h <= DAY_END_MIN / 60; h += 1) {
    ctx.fillText(`${String(h).padStart(2, '0')}:00`, x0 + ROW_HEADER_W + px(h * 60) + 4, axisY + 20);
  }

  // 일차별 행
  const rowsY = axisY + AXIS_H;
  for (let i = 0; i < dayCount; i += 1) {
    await drawDay(ctx, itinerary.days[i], places, x0, rowsY + i * (ROW_H + ROW_GAP));
  }

  // 하단 표시
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = C.sub;
  ctx.font = `500 12px ${FONT}`;
  ctx.fillText('여행 일정 플래너', x0, height - MARGIN - PAD + 26);

  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('toBlob failed'))), 'image/png');
  });
}

/** 파일 이름에 쓸 수 없는 문자를 뺀 "<제목>-타임라인.png" */
export function timelineFileName(itinerary: Itinerary): string {
  const safe = itinerary.title.replace(/[\\/:*?"<>|]/g, '').trim() || '여행';
  return `${safe}-타임라인.png`;
}

/** 브라우저 다운로드로 파일을 저장한다 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
