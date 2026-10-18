// 화면 개발용 더미 데이터. 실제 API 타입(src/types)과 같은 구조이며, 장소·후기 내용은 모두 가상이다.
import type { AuthorType, Itinerary, Place, Review, Visit } from '../types';

const place = (p: Omit<Place, 'thumbnail_url'>): Place => ({ ...p, thumbnail_url: null });

const placeList: Place[] = [
  place({
    id: 'p1', name: '성산일출봉', category: 'sight', address: '제주 서귀포시 성산읍', lat: 33.458, lng: 126.9425,
    description: '바다 위로 솟은 화산 분화구. 정상까지 약 30분 걸린다.', indoor: false,
    tags: ['사진 명소', '일출', '입장료'], checklist: ['편한 신발 챙기기', '입장 마감 시간 확인'],
  }),
  place({
    id: 'p2', name: '성산 바다식당', category: 'food', address: '제주 서귀포시 성산읍', lat: 33.4602, lng: 126.936,
    description: '갈치조림과 해물뚝배기를 파는 식당.', indoor: true,
    tags: ['해산물', '주차 가능'], checklist: ['웨이팅 주의'],
  }),
  place({
    id: 'p3', name: '섭지코지', category: 'sight', address: '제주 서귀포시 성산읍 고성리', lat: 33.4247, lng: 126.9306,
    description: '바다를 따라 걷는 산책로가 이어지는 해안 명소.', indoor: false,
    tags: ['산책', '바다 전망', '아이 동반 가능'], checklist: ['바람막이 챙기기'],
  }),
  place({
    id: 'p4', name: '바다앞 커피', category: 'cafe', address: '제주 서귀포시 성산읍', lat: 33.4301, lng: 126.9283,
    description: '통창으로 바다가 보이는 카페. 직접 구운 디저트가 있다.', indoor: true,
    tags: ['오션뷰', '디저트', '실내'], checklist: [],
  }),
  place({
    id: 'p5', name: '흑돼지 골목 식당', category: 'food', address: '제주 서귀포시 중앙로', lat: 33.25, lng: 126.56,
    description: '숯불 흑돼지 구이 전문점.', indoor: true,
    tags: ['흑돼지', '단체석', '실내'], checklist: ['예약 필요', '웨이팅 주의'],
  }),
  place({
    id: 'p6', name: '서귀포 오션 스테이', category: 'stay', address: '제주 서귀포시 칠십리로', lat: 33.246, lng: 126.563,
    description: '바다가 보이는 객실이 있는 숙소.', indoor: true,
    tags: ['오션뷰', '주차 가능', '조식'], checklist: ['체크인 15:00 이후', '주차 위치 확인'],
  }),
  place({
    id: 'p7', name: '제주 생활사 박물관', category: 'sight', address: '제주 서귀포시 서홍동', lat: 33.246, lng: 126.576,
    description: '제주의 옛 생활 모습을 전시한 박물관.', indoor: true,
    tags: ['실내', '아이 동반 추천', '비 오는 날'], checklist: ['휴관일 확인'],
  }),
  place({
    id: 'p8', name: '고기국수 식당', category: 'food', address: '제주 서귀포시 서홍동', lat: 33.25, lng: 126.555,
    description: '진한 육수의 고기국수를 파는 식당.', indoor: true,
    tags: ['국수', '실내', '주차 가능'], checklist: ['웨이팅 주의'],
  }),
  place({
    id: 'p9', name: '빛의 미디어아트관', category: 'activity', address: '제주 서귀포시 성산읍', lat: 33.29, lng: 126.41,
    description: '벽과 바닥 전체에 영상이 투사되는 몰입형 전시관.', indoor: true,
    tags: ['실내', '아이 동반 추천', '사진 명소'], checklist: ['온라인 예약 필요'],
  }),
  place({
    id: 'p10', name: '녹차 티하우스', category: 'cafe', address: '제주 서귀포시 안덕면', lat: 33.306, lng: 126.289,
    description: '녹차 음료와 디저트를 파는 대형 티하우스.', indoor: true,
    tags: ['녹차', '실내', '포토존'], checklist: [],
  }),
  place({
    id: 'p11', name: '서귀포 카약 체험', category: 'activity', address: '제주 서귀포시 보목동', lat: 33.238, lng: 126.53,
    description: '맑은 날 바다 위를 노 저어 다니는 카약 체험.', indoor: false,
    tags: ['야외', '체험', '친구·커플'], checklist: ['날씨에 따라 취소될 수 있음', '여벌 옷 챙기기'],
  }),
  place({
    id: 'p13', name: '해녀의 부엌', category: 'food', address: '제주 서귀포시 법환동', lat: 33.24, lng: 126.51,
    description: '해녀가 잡은 해산물로 차리는 식당.', indoor: true,
    tags: ['해산물', '실내', '주차 가능'], checklist: ['예약 필요'],
  }),
  place({
    id: 'p12', name: '협재 해변', category: 'sight', address: '제주 제주시 한림읍 협재리', lat: 33.394, lng: 126.239,
    description: '에메랄드빛 바다와 하얀 모래가 있는 해변.', indoor: false,
    tags: ['해변', '산책', '사진 명소'], checklist: ['선크림 챙기기'],
  }),
  place({
    id: 'p14', name: '협재 앞 카페', category: 'cafe', address: '제주 제주시 한림읍 협재리', lat: 33.395, lng: 126.241,
    description: '협재 해변이 보이는 작은 카페.', indoor: true,
    tags: ['오션뷰', '실내'], checklist: [],
  }),
];

const r = (
  place_id: string, n: number, author_type: AuthorType, rating: number,
  season: string, visit_time: string, text: string,
): Review => ({ review_id: `${place_id}-r${n}`, place_id, text, rating, author_type, season, visit_time });

const reviewList: Review[] = [
  r('p1', 1, '커플', 5, '가을', '오전', '아침 일찍 올라가니 사람이 적고 바다 색이 정말 예뻤어요.'),
  r('p1', 2, '가족', 3, '가을', '오후', '계단이 많아서 아이랑은 조금 힘들었어요.'),
  r('p2', 1, '친구', 4, '가을', '점심', '해물뚝배기 국물이 시원했어요. 점심엔 웨이팅이 좀 있어요.'),
  r('p2', 2, '혼자', 2, '가을', '점심', '그냥 그랬음.'),
  r('p3', 1, '가족', 5, '가을', '오후', '평지 산책로라 아이도 잘 걸었어요. 바람이 세니 겉옷 필수.'),
  r('p3', 2, '커플', 4, '가을', '오후', '사진 찍기 좋아요. 주차장에서 조금 걸어요.'),
  r('p4', 1, '커플', 5, '가을', '오후', '창가 자리에서 보는 바다가 최고. 디저트도 맛있었어요.'),
  r('p4', 2, '친구', 3, '가을', '오후', '자리가 금방 차서 기다렸어요.'),
  r('p5', 1, '친구', 5, '가을', '저녁', '고기가 두툼하고 직원분이 구워주셔서 편했어요.'),
  r('p5', 2, '가족', 3, '가을', '저녁', '맛은 좋은데 저녁엔 웨이팅이 길어요. 예약 추천.'),
  r('p6', 1, '커플', 5, '가을', '저녁', '객실에서 바다가 보여요. 조식도 괜찮았어요.'),
  r('p6', 2, '가족', 4, '가을', '저녁', '주차가 편했어요. 방음은 보통.'),
  r('p7', 1, '가족', 5, '가을', '오전', '비 오는 날 아이와 가기 좋았어요. 체험 코너가 있어요.'),
  r('p7', 2, '혼자', 4, '가을', '오전', '조용하게 둘러보기 좋아요.'),
  r('p8', 1, '혼자', 4, '가을', '점심', '국물이 진하고 양이 넉넉해요.'),
  r('p8', 2, '친구', 3, '가을', '점심', '무난한 맛.'),
  r('p9', 1, '가족', 5, '가을', '오후', '아이가 영상 속을 뛰어다니며 좋아했어요. 비 오는 날 추천.'),
  r('p9', 2, '커플', 4, '가을', '오후', '사진이 잘 나와요. 예약하고 가야 편해요.'),
  r('p10', 1, '친구', 4, '가을', '오후', '녹차 라떼가 진하고 포토존이 많아요.'),
  r('p10', 2, '가족', 3, '가을', '오후', '사람이 많아 조금 정신없었어요.'),
  r('p11', 1, '친구', 5, '가을', '오전', '바다가 잔잔한 날엔 정말 재밌어요. 강사님이 친절했어요.'),
  r('p11', 2, '커플', 2, '가을', '오전', '바람이 세서 중간에 취소됐어요.'),
  r('p13', 1, '커플', 5, '가을', '점심', '해산물이 신선하고 양이 많아요.'),
  r('p13', 2, '가족', 4, '가을', '점심', '예약 안 하면 기다려야 해요.'),
  r('p12', 1, '가족', 5, '가을', '오후', '물이 맑아서 아이가 오래 놀았어요.'),
  r('p12', 2, '혼자', 4, '가을', '오후', '해 질 무렵 산책하기 좋아요.'),
  r('p14', 1, '커플', 4, '가을', '오후', '해변이 보이는 자리가 좋아요. 자리는 적은 편.'),
  r('p14', 2, '친구', 3, '가을', '오후', '커피는 평범했어요.'),
];

const visit = (
  place_id: string, start: string, end: string, travel: number, reason: string, changed = false,
): Visit => ({
  place_id, start, end, travel_minutes_from_prev: travel, reason, changed,
  evidence_review_ids: [`${place_id}-r1`, `${place_id}-r2`],
});

export const mockPlaces: Record<string, Place> = Object.fromEntries(placeList.map((p) => [p.id, p]));
export const mockReviews: Record<string, Review> = Object.fromEntries(reviewList.map((x) => [x.review_id, x]));

export const mockItinerary: Itinerary = {
  title: '제주 3일 여행',
  region: '제주',
  companions: '커플',
  validation: { passed: 9, total: 10 },
  days: [
    {
      day: 1, date: '2026-11-14', weather: { condition: 'sunny', temp_max: 17, temp_min: 10 },
      visits: [
        visit('p1', '09:00', '10:30', 0, '일출봉은 오전에 사람이 적고 바다 전망이 좋다는 후기가 많아 첫 일정으로 배치했습니다.'),
        visit('p2', '11:00', '12:30', 10, '일출봉에서 가까운 식당이고, 해산물 국물 요리 후기가 좋습니다.'),
        visit('p3', '13:00', '14:30', 20, '맑은 날 산책하기 좋은 해안길이라 오후 야외 일정으로 골랐습니다.'),
        visit('p4', '15:00', '16:00', 15, '섭지코지 바로 옆이고 오션뷰 후기가 많아 휴식 시간으로 넣었습니다.'),
        visit('p5', '17:30', '19:00', 55, '저녁 식사로 흑돼지 구이 후기가 좋은 곳입니다. 예약이 필요합니다.'),
        visit('p6', '19:30', '22:00', 10, '식당과 가까운 오션뷰 숙소입니다.'),
      ],
    },
    {
      day: 2, date: '2026-11-15', weather: { condition: 'rain', temp_max: 14, temp_min: 9 },
      visits: [
        visit('p7', '09:30', '11:00', 0, '비 예보가 있어 실내 위주로 구성했고, 아이 동반 후기가 좋은 박물관입니다.'),
        visit('p8', '11:30', '12:30', 10, '박물관에서 가까운 실내 식당입니다.'),
        visit('p9', '13:30', '15:30', 25, '비 오는 날 실내에서 즐기기 좋은 전시라 야외 일정을 이 곳으로 교체했습니다.', true),
        visit('p10', '16:00', '17:00', 25, '실내 카페로 비 오는 오후에 쉬어가기 좋습니다.'),
        visit('p6', '18:00', '22:00', 40, '둘째 날 숙박입니다.'),
      ],
    },
    {
      day: 3, date: '2026-11-16', weather: { condition: 'cloudy', temp_max: 15, temp_min: 10 },
      visits: [
        visit('p11', '09:00', '11:00', 0, '흐리지만 바람이 약한 날이라 바다 체험을 넣었습니다.'),
        visit('p13', '11:30', '13:00', 15, '체험 후 해산물 식사로 후기가 좋은 곳입니다.'),
        visit('p12', '14:00', '15:30', 55, '서쪽으로 이동해 마지막 날 해변 산책으로 마무리합니다.'),
        visit('p14', '16:00', '17:00', 10, '협재 해변이 보이는 카페입니다.'),
      ],
    },
  ],
};
