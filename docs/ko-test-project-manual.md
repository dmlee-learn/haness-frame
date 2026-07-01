# haness-frame 테스트 프로젝트 생성 매뉴얼

이 문서는 `haness-frame`으로 테스트 프로젝트를 만들어 보고, 역할 기반 설계 문서를 생성하는 방법을 설명합니다.

현재 단계의 하네스는 다음을 지원합니다.

```text
1. 프로젝트별 하네스 엔지니어링 폴더 생성
2. 비즈니스 컨텍스트 문서 생성
3. Project Scout 선검색 백로그 생성
4. 역할별 설계 토론 문서 생성
5. 최종 의사결정 문서 생성
6. 구현 준비 문서 생성
```

아직 지원하지 않는 것:

```text
1. 실제 Google 자동 검색 실행
2. 검색 결과 자동 요약
3. 역할별 모델 자동 호출
4. 자동 코드 생성 루프
```

따라서 현재 테스트는 "프로젝트별 하네스 엔지니어링 작업공간을 만들고 설계 흐름을 검증하는 단계"입니다.

## 1. 작업 폴더로 이동

PowerShell에서 아래 폴더로 이동합니다.

```powershell
cd C:\Users\siwon\Documents\Codex\2026-06-28\dnls\work\haness-frame
```

## 2. 하네스 CLI가 동작하는지 확인

먼저 Python 파일에 문법 오류가 없는지 확인합니다.

```powershell
python -m py_compile .\src\haness_frame.py
```

역할 정의를 확인합니다.

```powershell
python .\src\haness_frame.py roles
```

설계 루프를 확인합니다.

```powershell
python .\src\haness_frame.py design-loop
```

## 3. 가장 쉬운 사용법

예를 들어 사용자가 이렇게 말한다고 가정합니다.

```text
사내업무시스템을 만들고 싶어요.
전자결재, 업무 요청, 문서 관리, 보고서 기능이 있으면 좋겠습니다.
```

이 경우 아래 명령 하나로 프로젝트 전용 하네스 엔지니어링 폴더를 생성합니다.

```powershell
python .\src\haness_frame.py create-project --project "internal-business-system" "전자결재, 업무 요청, 문서 관리, 보고서 기능을 가진 사내업무시스템 만들기"
```

생성 위치:

```text
projects/internal-business-system/
```

생성되는 구조:

```text
projects/internal-business-system/
  README.md
  context/
    business-context.md
    source-materials.md
  research/
    search-backlog.md
  docs/
    01-project-discovery.md
    02-role-discussion.md
    03-decision-record.md
  prompts/
    role-briefs.md
  implementation/
    README.md
```

이 구조가 "사내업무시스템 개발을 진행할 하네스 엔지니어링"입니다.

## 4. 생성 후 가장 먼저 할 일

아래 파일을 먼저 엽니다.

```text
projects/internal-business-system/README.md
```

그 다음 아래 순서대로 채웁니다.

```text
1. context/business-context.md
2. research/search-backlog.md
3. docs/01-project-discovery.md
4. docs/02-role-discussion.md
5. docs/03-decision-record.md
```

## 5. business-context.md 작성

`context/business-context.md`는 AI가 현재 상황과 비즈니스 맥락을 이해하게 만드는 문서입니다.

여기에 다음을 적습니다.

```text
Business Goal:
사내 업무 요청, 결재, 문서, 보고를 한 곳에서 관리한다.

Users:
임직원, 팀장, 관리자, 경영진

Current Workflow:
현재는 메신저, 엑셀, 이메일, 구두 보고가 섞여 있다.

Pain Points:
요청 누락, 결재 지연, 문서 버전 혼란, 보고 자료 재작성

Required Capabilities:
전자결재, 업무 요청, 담당자 지정, 상태 추적, 문서 첨부, 보고서

Excluded Scope:
급여, 회계, 인사평가 같은 ERP 전체 기능
```

## 6. search-backlog.md에서 선검색 수행

`research/search-backlog.md`에는 기본 Google 검색어가 자동 생성됩니다.

예:

```text
전자결재 업무 요청 문서 관리 보고서 사내업무시스템 만들기 existing projects
전자결재 업무 요청 문서 관리 보고서 사내업무시스템 만들기 open source github
전자결재 업무 요청 문서 관리 보고서 사내업무시스템 만들기 alternatives
전자결재 업무 요청 문서 관리 보고서 사내업무시스템 만들기 architecture
전자결재 업무 요청 문서 관리 보고서 사내업무시스템 만들기 common problems
```

현재는 자동 검색기가 없으므로 Google에서 직접 검색한 뒤 중요한 결과만 아래 형식으로 기록합니다.

```text
query:
provider:
url:
title:
excerpt:
retrieved_at:
confidence:
why_it_matters:
recommended_use:
```

## 7. 01-project-discovery.md 작성

`docs/01-project-discovery.md`는 Project Scout의 결과 문서입니다.

여기에 다음을 정리합니다.

```text
Related Projects:
유사한 사내업무시스템, 그룹웨어, 전자결재 제품

Existing Products:
Google Workspace, Microsoft 365, Notion, Jira Service Management 등

Open Source References:
참고 가능한 오픈소스 업무관리/문서관리 시스템

Reusable Ideas:
요청함, 승인 단계, 상태 추적, 권한 관리, 알림

Risks To Avoid:
권한 설계 실패, 결재 흐름 과복잡화, 문서 버전 충돌, 알림 과다
```

## 8. 02-role-discussion.md 작성

`docs/02-role-discussion.md`는 역할들이 설계를 토론하는 문서입니다.

역할별 책임:

```text
Context Curator:
비즈니스 맥락과 내부 자료를 정리

Researcher:
외부 검색 근거를 정리

Planner:
목표, 비목표, 제약, 설계 대안을 정리

Designer:
사용자 흐름과 화면/정보 구조를 설계

Architect:
시스템 구조, 데이터 흐름, 연동 방식을 검토

Critic:
실패 가능성, 약한 가정, 누락 테스트를 지적

Decision Maker:
최종 구현 방향을 결정
```

## 9. 03-decision-record.md 작성

`docs/03-decision-record.md`가 채워져야 구현을 시작합니다.

필수 항목:

```text
Accepted Decision:
이번 프로젝트에서 채택할 설계

Rejected Options:
버린 대안과 이유

Implementation Brief For Coder:
코더에게 전달할 구현 지시

Verification Commands:
검증할 명령 또는 테스트 기준

Rollback Plan:
문제가 생기면 되돌릴 방법
```

## 10. 기존 템플릿 명령

아래 명령은 단일 문서만 만들 때 사용합니다. 일반 사용자는 먼저 `create-project`를 쓰는 것이 더 쉽습니다.

### 설계 세션 문서만 생성

```powershell
python .\src\haness_frame.py design-template --write --project "pycapture-tool-pro" "Windows 화면 캡처, 영역 선택, OCR, 저장, 단축키를 지원하는 캡처 도구 만들기"
```

### 역할 토론 문서만 생성

```powershell
python .\src\haness_frame.py discuss --write --project "pycapture-tool-pro" "Windows 캡처 도구의 MVP 범위와 기술 구조 토론"
```

## 11. 테스트 프로젝트 이름 정하기

예를 들어 테스트 프로젝트를 `pycapture-tool-pro`라고 정합니다.

```text
프로젝트 이름:
pycapture-tool-pro

프로젝트 아이디어:
Windows에서 화면 캡처, 영역 선택, OCR, 저장, 단축키를 지원하는 캡처 도구
```

## 12. 설계 세션 문서 생성

아래 명령을 실행합니다.

```powershell
python .\src\haness_frame.py design-template --write --project "pycapture-tool-pro" "Windows 화면 캡처, 영역 선택, OCR, 저장, 단축키를 지원하는 캡처 도구 만들기"
```

문서는 아래 위치에 생성됩니다.

```text
projects/pycapture-tool-pro/docs/
```

파일 이름은 대략 아래 형식입니다.

```text
design-YYYYMMDD-HHMMSS-windows-ocr.md
```

## 13. 역할 토론 문서 생성

설계 세션보다 짧은 토론용 문서도 생성할 수 있습니다.

```powershell
python .\src\haness_frame.py discuss --write --project "pycapture-tool-pro" "Windows 캡처 도구의 MVP 범위와 기술 구조 토론"
```

생성 위치는 동일합니다.

```text
projects/pycapture-tool-pro/docs/
```

## 14. 생성된 문서에서 먼저 채울 부분

생성된 설계 문서에서 가장 먼저 봐야 할 섹션은 다음입니다.

```text
## 1. Project Discovery - Project Scout
```

이 섹션에는 기본 Google 검색 질의가 들어 있습니다.

예:

```text
1. Windows 화면 캡처 도구 existing projects
2. Windows 화면 캡처 도구 open source github
3. Windows 화면 캡처 도구 alternatives
4. Windows 화면 캡처 도구 architecture
5. Windows 화면 캡처 도구 common problems
```

현재는 자동 검색기가 없으므로, 사용자가 직접 Google에서 검색한 뒤 결과를 문서에 붙여 넣습니다.

## 15. 검색 결과 기록 형식

검색 결과는 아래 형식으로 기록합니다.

```text
query:
provider:
url:
title:
excerpt:
retrieved_at:
confidence:
```

예시:

```text
query: Windows screenshot tool open source github
provider: google
url: https://github.com/example/example-capture-tool
title: Example Capture Tool
excerpt: Windows screenshot utility with region capture and hotkeys.
retrieved_at: 2026-07-01
confidence: medium
```

검색 결과를 그대로 많이 붙여 넣기보다는, 설계에 영향을 주는 내용만 요약해서 기록합니다.

## 16. Project Scout가 정리해야 하는 내용

선검색 후 아래 항목을 채웁니다.

```text
Related projects:
Existing products:
Open source repositories:
Useful implementation patterns:
Risks to avoid:
```

예:

```text
Related projects:
- ShareX: Windows용 고급 캡처/업로드 도구
- Flameshot: 영역 선택 중심의 캡처 도구

Useful implementation patterns:
- 전역 단축키
- 영역 선택 오버레이
- 캡처 후 편집 화면
- 저장/클립보드/업로드 동작 분리

Risks to avoid:
- 권한 문제
- 멀티 모니터 DPI 처리
- OCR 처리 지연
- 단축키 충돌
```

## 17. Planner 섹션 작성

그 다음 `Planner`가 아래를 정리합니다.

```text
Goals:
Non-goals:
Constraints:
Unknowns:
Discovery summary to use:
```

예:

```text
Goals:
- Windows에서 빠르게 영역 캡처
- 캡처 이미지를 파일 또는 클립보드로 저장
- OCR은 MVP 이후 기능으로 분리 검토

Non-goals:
- 클라우드 업로드
- 이미지 편집기 전체 기능
- 팀 협업 기능

Constraints:
- Windows 우선
- 로컬 실행
- 단축키 지원 필요

Unknowns:
- 어떤 GUI 프레임워크를 사용할지
- OCR 엔진을 무엇으로 할지
- 멀티 모니터 DPI 처리를 어떻게 할지
```

## 18. Designer, Architect, Critic 순서로 작성

이후 문서는 아래 순서로 채웁니다.

```text
Designer:
사용자 흐름, 화면 구조, 혼란스러운 상태, UX 위험 정리

Architect:
기술 구조, 모듈 분리, 데이터 흐름, 운영 리스크 정리

Critic:
실패 가능성, 약한 가정, 누락된 테스트, 진행 가능 여부 검토
```

## 19. Decision Maker가 최종 결정 작성

마지막으로 아래 섹션을 작성합니다.

```text
Accepted decision:
Rejected options:
Implementation brief:
Verification commands:
Rollback plan:
```

이 섹션이 채워진 뒤에만 `Coder`가 구현을 시작하는 것이 원칙입니다.

## 20. 전체 테스트 절차 요약

```text
1. haness-frame 폴더로 이동
2. py_compile로 CLI 확인
3. design-template 명령으로 설계 문서 생성
4. discuss 명령으로 토론 문서 생성
5. Project Scout 섹션에서 Google 선검색 수행
6. 관련 프로젝트, 대안, 오픈소스, 리스크 기록
7. Planner가 목표/제약/미지수를 정리
8. Designer, Architect, Critic이 각각 검토
9. Decision Maker가 최종 구현 방침 결정
10. 결정된 구현 브리프를 Coder에게 전달
```

## 21. 현재 단계에서 좋은 테스트 주제

처음에는 너무 큰 프로젝트보다 작은 도구가 좋습니다.

추천 테스트 주제:

```text
- Windows 화면 캡처 도구
- 로컬 Markdown 노트 앱
- 폴더 파일 정리 도구
- 이미지 일괄 리사이즈 도구
- 로컬 LLM 프롬프트 테스트 도구
```

너무 큰 주제:

```text
- 완전한 IDE 만들기
- Slack 같은 협업 서비스 만들기
- Figma 같은 디자인 도구 만들기
- 전체 ERP 시스템 만들기
```

처음 테스트 목적은 코드를 바로 만드는 것이 아니라, 하네스가 좋은 설계 문서를 만들 수 있는지 확인하는 것입니다.
