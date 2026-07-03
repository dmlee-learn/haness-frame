# haness-frame 테스트 프로젝트 매뉴얼

이 문서는 `haness-frame`으로 프로젝트 작업공간을 만들고 검증하는 방법을 설명합니다.

## 현재 지원하는 흐름

1. 프로젝트별 하네스 작업공간 생성
2. 비즈니스 컨텍스트, 백로그, discovery, discussion, decision, implementation 문서 생성
3. `summary`, `search-plan`, `evidence-draft`, `evidence-gaps`로 증거 작업 시작
4. `add-evidence` 또는 `evidence-commit`으로 구조화된 evidence 등록
5. `decision-draft`로 decision record 재생성
6. `verify`로 작업공간 검증

## 아직 자동화되지 않은 부분

1. 실제 Google 검색 실행
2. 검색 결과 자동 요약
3. 모든 단계를 위한 자동 멀티모델 호출
4. 완전한 자율 코드 생성 루프

## 테스트 프로젝트 생성

리포지토리 루트에서 실행합니다.

```powershell
python .\src\haness_frame.py create-project --project "internal-business-system" "결재, 업무, 문서, 보고를 지원하는 내부 업무 시스템을 구축한다"
```

## 런타임 검증

프로젝트를 만든 뒤 아래 명령으로 흐름을 점검합니다.

```powershell
cd .\projects\internal-business-system
python app.py summary
python app.py search-plan
python app.py evidence-draft
python app.py evidence-gaps
python app.py decision-draft
python app.py verify
```

## 실무 규칙

구현에 들어가기 전에 evidence 수집과 decision gate 검증까지 한 번은 통과시키는 흐름으로 유지합니다.

