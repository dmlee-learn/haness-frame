# haness-frame 테스트 절차

## 목적
개발이 진행되는 동안 하네스 런타임, 생성된 프로젝트, 결정 게이트를 같은 상태로 맞춰 둡니다.

## 테스트 순서
1. 생성기 작업공간에서 `python -m compileall src`를 실행합니다.
2. 생성된 프로젝트에서 `python app.py summary`를 실행해 개수와 다음 작업을 확인합니다.
3. `python app.py search-plan`으로 계획, evidence 초안, gap 보고서를 갱신합니다.
4. `research/search-evidence-draft.md`와 `research/search-evidence-gaps.md`를 검토합니다.
5. `python app.py add-evidence ...` 또는 `python app.py evidence-commit`으로 evidence를 채웁니다.
6. `python app.py decision-draft`로 decision record를 다시 생성합니다.
7. `python app.py verify`로 compileall, manifest 검증, decision gate를 확인합니다.
8. 런타임 템플릿이 바뀌면 `python scripts/sync_generated_projects.py`를 실행합니다.

## 각 명령의 의미
- `compileall`: 생성기에서 문법 또는 import 수준의 깨짐이 있는지 확인합니다.
- `summary`: 문서, evidence, gap, gate 상태가 어떤지 확인합니다.
- `search-plan`: 백로그가 기대한 검색 대상들을 계속 내는지 확인합니다.
- `evidence-draft`와 `evidence-gaps`: 아직 조사와 증거 수집이 더 필요한지 확인합니다.
- `evidence-commit`: 초안을 스키마 흔들림 없이 구조화된 evidence로 바꿀 수 있는지 확인합니다.
- `decision-draft`: 현재 컨텍스트에서 accepted decision과 implementation brief를 다시 만들 수 있는지 확인합니다.
- `verify`: 현재 프로젝트가 다음 단계로 넘어갈 준비가 되었는지 확인합니다.

## 실무 규칙
- 템플릿을 바꾸기 전후로 생성 프로젝트에서 `summary`와 `verify`를 둘 다 실행합니다.
- 코드 수정 뒤에는 생성기 작업공간에서 `compileall`을 실행합니다.
- 런타임 템플릿을 바꾼 뒤에는 `sync_generated_projects.py`를 실행합니다.
