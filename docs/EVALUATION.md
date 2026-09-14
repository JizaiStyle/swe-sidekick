# 実務評価とホスト選択型リードの計測方法

## 対象プロジェクトからの呼出

SWE Sidekickを起動した現在のホストがリードであり、Codexホストでも
Devinホスト上のユーザー選択モデル（Fableを含む）でもよい。リードは
設計・レビュー・採否を担当し、ラッパーは明示的に設定したSWE-2 workerへ
範囲を限定した実装を委譲する。リードのモデルや推論設定は現在のホストで
選択し、ラッパーや評価記録から推測・変更しない。

```text
Codex: $swe-sidekick
Devin: /swe-sidekick
```

DevinでFableをリードにする場合は、`/swe-sidekick`の前にユーザーが
`/model`または`devin --model <catalog-id>`で、現在利用できるソロFableの
正確なカタログ値を選ぶ。workerのSWE-2設定とは別の選択である。複合モデル
や自動ルーティングの選択を、この評価の実績や設定として扱わない。

## 記録の流れ

1. 実務タスク開始時に、受入条件・変更範囲・課題種別とリードホストを確定
   する。開始時刻と使用量表示を確認できた場合だけ観測値を控え、確認を
   忘れた時刻や待ち時間を後から推測しない。
2. `prepare → run → inspect → リードの独立レビュー → verify → reviewed hash
   を指定したapply`を実行する。失敗時も理由を記録する。`incomplete_no_changes`
   は正常完了ではなく、検証やapplyへ進めない。
3. セクションの担当リードを変える場合は、実行中の作業を止めてから
   `handoff --task <task-id>`を読み取り専用で実行する。JSONと次の目的を
   次のホストへ私的に渡し、新しいリードが現在のstate、差分、patch hash、
   検証状態を確認してから明示的な次の操作を決める。会話履歴、モデル文脈、
   prompt cacheはホスト間で移行しない。共有タスクには検証済みworker sessionと
   retry予算が残るが、新しいリードがresumeやapplyを自動実行することはない。
4. 実務終了・中断・リードへの引き取り時に、[JSON見本](../examples/evaluation-record.json)
   を使って、観測した値だけのレコードを元repo外へ保存する。`task_id`には
   実際のローカルタスクIDを入れるが、公開リポジトリや公開ログへ保存しない。
5. `swe-sidekick evaluate --task <task-id> --record <absolute-json-path>`で
   記録する。既存記録を訂正する時だけ内容を確認して`--replace`を追加する。
6. `swe-sidekick evaluation-report`で現在のローカルレポートを生成する。
   `--include-smoke`は診断用で、実務成績には含めない。

実績の正本はローカルな
`~/.local/state/codex-swe-sidekick/tasks/<task-id>/state.json`と
`evaluation.json`である。レポートはこの正本から生成し、手作業の成績表を
公開ツリーへ複製しない。評価記録はタスクを実行せず、ログを解析して値を
補完せず、元のsource projectを変更しない。raw trajectory、workerログ、
handoff snapshotは私的なローカルデータとして扱う。

## フィールドと判断

- `schema_version`は1、`task_id`は実際のローカルタスクIDとする。未知値は
  JSONの`null`にし、0は実測で0だった場合だけ記録する。
- `acceptance_met`はリードが要件と実際の差分を独立に確認した結果、
  `independent_tests_passed`はリードが実行した独立検証の結果、
  `post_apply_tests_passed`は元repoへ反映後の検証結果である。workerの申告、
  終了コード、scopeフラグ、applyだけを理由にtrueにしない。
- `lead_review_minutes`は、そのタスクの差分をリードがレビューした実測時間、
  `total_minutes`はタスクの開始から完了・中断・引き取りまでの実測時間である。
  どちらもCodex専用ではなく、CodexまたはDevin/Fableの現在のリードに適用する。
  worker秒数から換算しない。複数ホストでセクションを担当した場合、すべての
  区間を観測できた時だけ合計し、欠けた区間がある値は`null`にしてnotesへ
  計測範囲を短く記す。
- `parent_model`、`parent_effort`、`parent_model_evidence`は、現在のリード
  ホストで実際に確認した場合だけ3項目すべてを埋める。想定値、ユーザーの希望、
  前の会話、固定のモデル/推論強度の組合せを証拠として転記しない。確認できない場合は
  3項目とも`null`とする。ホストをまたぐタスクでは、各区間のモデル情報を
  notesで区別し、単一の未確認値にまとめない。
- `codex_usage_before`と`codex_usage_after`はCodexホストで直接観測した使用量
  のみを記録する欄である。Devin/Fableの値をCodex欄へ代入しない。Fableについて
  その欄の意味を満たす同等の事実を直接確認でき、対象範囲・単位・時刻を明示
  できる場合を除き、Fableでは`null`とする。
- `devin_usage_before`と`devin_usage_after`はDevinで直接表示・確認した使用量
  のみを記録する。workerの経過秒数、ターン数、モデル出力文から使用量や課金を
  推測しない。確認できない値は`null`とし、並行作業を含むアカウント全体の表示は
  notesに対象範囲を記録してタスク単価へ変換しない。
- `observed_total_cost_usd`は、当該タスクのリードとworkerを含む総費用を実際に
  確認できた場合だけ設定し、`cost_evidence`に表示・単位・対象範囲を記す。
  Devin側だけの表示、定額利用枠、トークン数、無料枠、worker秒数から総費用を
  推定しない。
- `notes`には課題種別、リードホスト、受入確認、失敗・引き取り理由、計測範囲、
  欠測理由を短く残す。認証情報、会話全文、ローカル個人パス、実タスクID、raw
  ログ、非公開ベンチマーク値は書かない。

自動取得されるworker実行秒数、選択モデル、export報告値、ターン数は、親リードの
レビュー時間・総時間・使用量とは別の指標である。モデルexportは証拠の一部だが、
provider側の課金やホストの設定を単独では証明しない。失敗・未評価も一覧に含める。
率を見る時は分母と未評価件数を同時に確認する。観測された値だけの平均には観測
件数と欠損件数を併記し、全欠損を0にしない。`rates.accepted`は受入件数/実行済み
件数、`accepted_among_assessed`は評価済み件数を分母とする補助指標である。
再試行後の最終結果を受入判定に使い、過去の失敗は`failed_attempts`と`retries`へ
残す。中断や明示した不合格は失敗または未知として扱い、成功へ読み替えない。

## 比較の限界

このローカル評価は、別の課題・採点方法・リポジトリ・リードホスト・モデル・
推論強度・課金条件で得た外部結果と同じ尺度ではない。Devinのnative Fusion製品を
このwrapperの実行結果として扱わず、Fusion/compositeの実行や追加の課金実験を
評価のために行わない。公開資料に言及する場合も背景情報にとどめ、実務の受入率、
速度、費用、worker時間からFusionとの勝率・相対速度・削減率を計算しない。

各実務タスクの報告には、実際の修正、独立テスト、受入結果、残る問題、現在の
リード設定の確認状況、workerの選択・export確認、観測したレビュー時間・総時間・
使用量、全件数・未評価件数・再試行傾向、そして比較可能な範囲を短くまとめる。
リードモデル、Fable相当値、使用量、費用が不明なら、そのまま`null`として報告する。
少数の実務例は適性を見つける材料であり、優位性の証明ではない。
