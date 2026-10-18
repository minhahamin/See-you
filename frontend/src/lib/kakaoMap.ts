let loading: Promise<void> | null = null;

/** 카카오맵 SDK를 한 번만 불러온다. 이미 불러왔으면 바로 끝난다. */
export function loadKakaoMaps(appKey: string): Promise<void> {
  if (window.kakao?.maps?.LatLng) return Promise.resolve();
  if (loading) return loading;

  loading = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    // autoload=false: 스크립트 로딩이 끝난 뒤 kakao.maps.load 콜백에서 객체를 쓴다
    script.src = `//dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(appKey)}&autoload=false`;
    script.async = true;
    script.onload = () => {
      if (!window.kakao) {
        loading = null;
        reject(new Error('Kakao Maps SDK global not found'));
        return;
      }
      window.kakao.maps.load(() => resolve());
    };
    script.onerror = () => {
      loading = null;
      script.remove();
      reject(new Error('Failed to load Kakao Maps SDK'));
    };
    document.head.appendChild(script);
  });
  return loading;
}
