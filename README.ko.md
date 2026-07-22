# haness-frame

로컬 AI를 이용해 신뢰할 수 있는 소프트웨어를 만들기 위한 하네스 엔지니어링 프레임워크입니다.

영문 문서: [README.md](README.md)

## 목표

사용자의 요청을 구현 가능한 결정으로 정리하고, 로컬 AI가 코드 생성, 테스트,
검토와 제한된 수정 루프를 수행하도록 지원합니다. 한 모델이 계획, 구현, 테스트와
자기 평가를 모두 한 번에 처리하지 않도록 역할과 실행 기록을 분리합니다.

핵심 원칙은 다음과 같습니다.

- 로컬 AI를 기본으로 사용하고 클라우드 모델은 선택적으로 사용합니다.
- 구현 전에 범위, 근거와 결정 내용을 기록합니다.
- 구현에는 실행 가능한 검증 명령이 있어야 합니다.
- 실패한 검증은 제한된 진단, 패치와 재시험 루프로 처리합니다.
- 사용자의 기존 변경을 보존하고 패치, 테스트와 판정 이력을 기록합니다.
- 소규모 작업은 짧게, 중요한 작업은 엄격하게 실행할 수 있도록 확장합니다.

## 프로젝트 생성

저장소 루트에서 실행합니다.

```powershell
python .\src\haness_frame.py create-project `
  --project sample-project `
  "테스트가 포함된 Python CLI 계산기 만들기"
```

생성 경로:

```text
work/haness-frame/projects/sample-project
```

한국어 요청으로 생성하면 기본 영문 `README.md`와 함께 `README.ko.md`가
생성됩니다. 영어 요청은 기본 `README.md`만 생성합니다.

## 로컬 AI 설정 확인

생성한 프로젝트 폴더에서 실행합니다.

```powershell
python app.py check
python app.py live-check --role planner
```

`check`는 서비스 구성과 endpoint를 검사하고, `live-check`는 실제 역할 호출을
한 번 수행합니다. 서비스 설정은 `workspace/services.json`에 있습니다.

## 주요 실행 흐름

엄격한 흐름은 다음 순서로 진행합니다.

1. 프로젝트 문맥과 검색 계획 확인
2. 구조화된 evidence와 claim 기록
3. 역할 토론과 결정 생성
4. decision gate 확인
5. coder 패치 생성과 적용
6. 테스트, qualification과 archive 검증

상태 확인:

```powershell
python app.py summary
python app.py runs --unresolved
python app.py gate
```

## 한 줄 구현

결정 게이트가 열리고 검증 정책이 승인된 이후에는 다음 한 줄로 구현부터 최종
archive 검증까지 실행할 수 있습니다.

```powershell
.\run.ps1 implement --task "승인된 기능 구현"
```

이 명령은 다음 작업을 수행합니다.

- 로컬 coder 호출
- unified diff hunk 줄 수 자동 보정
- 수정 가능 경로와 패치 검증
- 적용 전 스냅샷 생성
- 패치 적용과 승인된 테스트 실행
- qualification 실패 시 패치 롤백
- 성공 시 archive 생성과 무결성 검사

코드가 이미 적용된 프로젝트의 최종 검증은 다음 한 줄로 실행합니다.

```powershell
.\run.ps1 finish
```

## 수동 검증과 수정

```powershell
python app.py verification-plan
python app.py verification-run
python app.py repair-run --task "실패한 구현 수정" --max-attempts 2
python app.py qualify --run-verification
python app.py archive
python app.py archive-verify
```

`workspace/verification-policy.json`에 정확히 승인된 명령만 실행됩니다. 패치는
`workspace/repair-policy.json`에 지정된 경로와 크기 제한을 따라야 합니다.

## 주요 폴더

```text
config/                     모델 endpoint와 역할 정책
docs/                       구조, 로드맵과 한영 매뉴얼
localdoc/                   개발 목표와 테스트 과정 기록
scripts/                    서비스 확인과 동기화 스크립트
src/haness_frame_app/       프로젝트 생성기와 애플리케이션 코드
src/haness_frame_app/templates/runtime/
                            생성 프로젝트에 포함되는 실행 엔진
work/haness-frame/projects/ 생성된 프로젝트
```

## 개발 검증

```powershell
python -m unittest discover -s tests
python -m compileall -q src tests
```

상세 매뉴얼:

- `docs/test-project-manual.ko.md`
- `docs/test-project-manual.en.md`
- `localdoc/development-goal-summary.ko.md`
- `localdoc/testing-process.ko.md`
