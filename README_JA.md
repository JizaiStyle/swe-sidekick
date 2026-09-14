# SWE Sidekick

[チートシート（英語）](docs/CHEATSHEET.md)

**CodexまたはDevin/Fableを親、SWE-2を実装担当にする明示起動型Skill**です。親が計画・レビュー・採否を担当し、範囲を限定した実装を公式Devin CLIへ委譲します。独立したGitスナップショットで作業し、差分の範囲・検証結果・レビュー済みハッシュを確認してから適用します。

Devin標準のFusionとは別の仕組みです。親モデルは現在のセッションで選択したものを使います。macOS/Linux、Python 3.10以上、Git、インストール・ログイン済みのDevin CLIが必要です。

## インストール

```sh
git clone https://github.com/JizaiStyle/swe-sidekick.git
cd swe-sidekick
python3 install.py
python3 install.py --apply
```

既存の管理対象インストールを更新する場合は、`python3 install.py --upgrade`で確認し、`python3 install.py --upgrade --apply`で適用します。変更済み・所有不明のファイルは上書きせず、更新時のバックアップと失敗時のロールバックを行います。

CLIは`~/.local/bin/swe-sidekick`、Codex向けSkillは`~/.codex/skills/swe-sidekick`、Devin向けは`~/.config/devin/skills/swe-sidekick`に配置します。`~/.local/bin`をPATHへ追加し、必要ならホストのセッションを開き直してください。グローバルのモデル設定や既存タスクは変更しません。

## 使い方

- Codexでは`$swe-sidekick`を明示して依頼します。
- Devinでは`/model`で利用可能なFableモデルを選択し、`/swe-sidekick`を実行します。

初回は`swe-sidekick doctor`でモデル一覧を確認し、実際に表示されたSWE-2のモデル名またはIDを`swe-sidekick configure --model 'SWE-2 High' --acknowledge-usage`のように指定します。名称は利用環境のカタログを優先します。モデル実行はDevinへコード・指示を送信し、利用枠やクレジットを消費する可能性があります。

クリーンな信頼済みGitリポジトリを対象に、許可するファイルと合格条件を決めて依頼してください。処理は`prepare → run → inspect → 親のレビュー → verify → ハッシュを指定してapply`です。自動のコミット・push・公開は行いません。

## セクションごとに親を変える

**可能です。別セッションで順番に引き継ぎます。** Codex親の作業を止め、`swe-sidekick handoff --task TASK_ID`のJSONと次の目的を、新しいDevin/Fable親へ渡します。逆方向も同じです。新しい親は現在の差分と検証結果を確認してから続けます。

同一タスクを複数の親で同時に進めないでください。会話履歴・モデルの内部状態・キャッシュは自動移行しません。引き継ぎJSONにはローカルパスやタスク情報が含まれるため、公開リポジトリには保存しません。詳細は[ホストと引き継ぎ](docs/HOSTS.md)を参照してください。

同じタスクの続きは、元の目的・許可ファイルの範囲内に限ります。目的や対象範囲を変える場合は、クリーンなリポジトリから新しいタスクを作成します。

「Codex」がDevin内で選択できるモデルを指す場合は、Devinの`/model`で利用可能な親モデルを切り替える方法もあります。CodexアプリとDevinアプリの間を移る場合とは区別してください。

[安全性の範囲](SECURITY.md)、[検証記録](TEST_REPORT.md)、[計測方法](docs/EVALUATION.md)も参照してください。実モデルでの互換性や速度・トークン・費用の削減は、オフライン試験だけでは確認できません。

要求の正本は[MASTER_PLAN.md](docs/MASTER_PLAN.md)、進捗の正本は[ROADMAP.md](docs/ROADMAP.md)です。開発時には関連要件と検証根拠を更新します。[英語README](README.md)にインストール解除と開発手順を記載しています。
