정리하면, 지금 하네스 엔지니어링 시스템은 **골격은 꽤 잡혔고**, 아직 **실제 AI 실행 엔진**과 **운영 안정화**가 남아 있습니다.

**1. 지금까지 개발된 것**
- 프로젝트 생성기
- 웹 UI 기반 프로젝트 생성/관리
- 프로젝트 ZIP 다운로드
- AI 서비스 DB 설정 저장
- 역할별 서비스 매핑
- 프로젝트별 역할 라우팅 저장
- `workspace/state.json`
- `workspace/services.json`
- `workspace/manifest.json`
- `workspace/scorecard.json`
- `AGENTS.md`, `CLAUDE.md`, `SKILL.md`
- 역할별 템플릿 문서 분리
- `app.py` 기반 프로젝트 실행 진입점
- `harness_app` 패키지 형태의 실행 골격

**2. 아직 개발해야 할 것**
- 실제 AI 호출 엔진
  - 역할별로 `base_url`, `model`, `provider_type`를 읽어서 API 요청 전송
  - OpenAI-compatible, Ollama, Codex, Anthropic 분기 처리
- 프롬프트 조립기
  - role packet + 프로젝트 문서 + 컨텍스트 주입
- 응답 파서
  - 일반 텍스트
  - tool call
  - 실패/재시도
- 작업 오케스트레이터
  - project_scout -> researcher -> planner -> designer -> architect -> critic -> decision_maker -> coder 흐름
- 외부 검색 연동
  - 검색 결과 저장
  - 검색 증거 파일화
- 프로젝트 상태 자동 갱신
  - scorecard 갱신
  - manifest 기준 체크
- 테스트 체계
  - 최소 smoke test
  - role routing test
  - service snapshot test
- 로그/디버그/감사 기록
  - 어떤 역할이 어떤 서비스와 어떤 응답을 썼는지 추적
- 실패 복구
  - API 실패 시 fallback service 사용
  - 재시도 정책
  - timeout 정책

**3. 있으면 좋은 것**
- 모델 라우터
  - 역할별로 모델 자동 추천
- 작업 큐
  - 여러 프로젝트 동시 처리
- 자동 검색 워크플로우
  - 검색 -> 요약 -> 토론 -> 결정 순환
- 승인 게이트
  - coder 실행 전 decision record 승인 필수
- 버전별 스냅샷
  - 프로젝트 상태 롤백
- 정책 편집 UI
  - 역할별 provider와 제한값 조정
- 자동 백업 ZIP
  - 프로젝트 완료 시 아카이브 생성
- 다국어 확장
  - 한국어/영어 외 추가 언어팩
- 외부 에이전트 연동
  - Cline, Claude, Codex, Ollama, vLLM 공통 인터페이스

**4. 우선순위**
1. 실제 AI 호출 엔진
2. 프롬프트 조립기
3. 응답 파서와 fallback
4. 오케스트레이터
5. 검색 연동
6. 테스트/로그/감사
7. 자동 상태 갱신
8. 편집 가능한 운영 UI 고도화
9. 자동 백업과 아카이빙
10. 다국어/고급 편의 기능

**5. Phase별 계획**

**Phase 1: 실행 가능화**
- 역할별 AI 호출 구현
- `workspace/services.json` 읽기
- 서비스별 `base_url`, `model` 적용
- 실패 시 fallback 적용
- 최소 응답 기록 저장

**Phase 2: 하네스 흐름**
- 역할 순차 실행
- project_scout -> researcher -> planner -> designer -> architect -> critic -> decision_maker -> coder
- 각 단계 산출물 파일화
- decision gate 추가

**Phase 3: 안정성**
- timeout, retry, error classification
- scorecard 기록
- manifest 검증
- smoke test 추가
- 실행 로그 저장

**Phase 4: 검색/토론 통합**
- Google 검색 결과 수집
- 증거 문서화
- 토론 문서 자동 생성
- 역할별 evidence injection

**Phase 5: 운영성**
- 프로젝트 상태 대시보드
- 서비스 설정 변경 UI
- 롤별 서비스 추천
- 프로젝트별 서비스 교체
- ZIP 백업 자동화

**Phase 6: 확장**
- tool call 지원
- 멀티 모델 라우팅
- 자동 요약/검토 루프
- 외부 런타임 연동
- 다국어 확장

현재 기준으로는 **Phase 1이 가장 중요**합니다.  
지금까지는 “하네스를 만들 수 있는 시스템”을 만들었고, 다음은 “하네스가 실제로 일하는 실행기”를 만드는 단계입니다.

원하면 다음 턴에 이걸 바로 `docs/roadmap.md` 형식으로 저장용 문서로 바꿔서 넣겠습니다.