// 카카오맵 JavaScript SDK 중 이 프로젝트가 쓰는 부분만 선언한다.
// 시그니처 출처: https://apis.map.kakao.com/web/documentation/
declare namespace kakao.maps {
  class LatLng {
    constructor(latitude: number, longitude: number);
  }

  class LatLngBounds {
    constructor();
    extend(point: LatLng): void;
  }

  interface MapOptions {
    center: LatLng;
    level?: number;
  }

  class Map {
    constructor(container: HTMLElement, options: MapOptions);
    setBounds(
      bounds: LatLngBounds,
      paddingTop?: number,
      paddingRight?: number,
      paddingBottom?: number,
      paddingLeft?: number,
    ): void;
    relayout(): void;
  }

  interface PolylineOptions {
    path: LatLng[];
    strokeWeight?: number;
    strokeColor?: string;
    strokeOpacity?: number;
    strokeStyle?: string;
  }

  class Polyline {
    constructor(options: PolylineOptions);
    setMap(map: Map | null): void;
  }

  interface CustomOverlayOptions {
    map?: Map;
    position: LatLng;
    content: HTMLElement | string;
    xAnchor?: number;
    yAnchor?: number;
    zIndex?: number;
    clickable?: boolean;
  }

  class CustomOverlay {
    constructor(options: CustomOverlayOptions);
    setMap(map: Map | null): void;
  }

  /** autoload=false로 SDK를 불러왔을 때 로딩이 끝난 뒤 callback을 실행한다. */
  function load(callback: () => void): void;
}

interface Window {
  kakao?: typeof kakao;
}
