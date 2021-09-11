import re
from collections import defaultdict
from typing import DefaultDict, List, Optional

import pendulum

from ja_timex.extract_filter import BaseFilter, DecimalFilter, NumexpFilter, PartialNumFilter
from ja_timex.number_normalizer import NumberNormalizer
from ja_timex.tag import TIMEX, Extract
from ja_timex.tagger import AbstimeTagger, DurationTagger, ReltimeTagger, SetTagger
from ja_timex.util import detect_range_expression_before_timex


class TimexParser:
    def __init__(
        self,
        number_normalizer=NumberNormalizer(),
        abstime_tagger=AbstimeTagger(),
        duration_tagger=DurationTagger(),
        reltime_tagger=ReltimeTagger(),
        set_tagger=SetTagger(),
        custom_tagger=None,
        pattern_filters: List[BaseFilter] = [NumexpFilter(), PartialNumFilter(), DecimalFilter()],
        reference: Optional[pendulum.DateTime] = None,
        ignore_kansuji: bool = False,
    ) -> None:
        self.number_normalizer = number_normalizer
        self.abstime_tagger = abstime_tagger
        self.duration_tagger = duration_tagger
        self.reltime_tagger = reltime_tagger
        self.set_tagger = set_tagger
        self.custom_tagger = custom_tagger
        self.reference = reference
        self.pattern_filters = pattern_filters

        self.number_normalizer.set_ignore_kansuji(ignore_kansuji)

        self.all_patterns = {}
        if self.custom_tagger:
            self.all_patterns["custom"] = self.custom_tagger.patterns
        self.all_patterns["abstime"] = self.abstime_tagger.patterns
        self.all_patterns["duration"] = self.duration_tagger.patterns
        self.all_patterns["reltime"] = self.reltime_tagger.patterns
        self.all_patterns["set"] = self.set_tagger.patterns

    def parse(self, raw_text: str) -> List[TIMEX]:
        """入力文字列からTIMEXを抽出する

        Args:
            raw_text (str): 入力文字列

        Returns:
            List[TIMEX]: 抽出されたTIMEXのリスト
        """
        # 数の認識/規格化
        self.processed_text = self._normalize_number(raw_text)

        # 時間表現の抽出
        all_extracts = self._extract(self.processed_text)
        filtered_extracts = self._extract_filter(all_extracts, self.processed_text)
        type2extracts = self._drop_duplicates(filtered_extracts, self.processed_text)

        # ExtractからTimexへの規格化
        timex_tags = self._parse(type2extracts)

        # 規格化後のタグの情報付与
        timex_tags = self._modify_renge_start_and_end(timex_tags, self.processed_text)
        timex_tags = self._extract_abbrev_patten(timex_tags, self.processed_text)
        timex_tags = self._modify_additional_information(timex_tags)

        return timex_tags

    def _normalize_number(self, raw_text: str) -> str:
        """数字の表記ゆれを正規化するする

        NumberNormalizerはコンストラクタ内でset_ignore_kansuji()メソッドにより、漢数字を変換するかどうかのフラグが付与される

        Args:
            raw_text (str): 入力文字列

        Returns:
            str: 正規化された入力文字列
        """
        return self.number_normalizer.normalize(raw_text)

    def _extract(self, processed_text: str) -> List[Extract]:
        """入力文字列から候補となるExtractをすべて抽出する

        Args:
            processed_text (str): 入力文字列

        Returns:
            List[Extract]: 抽出されたExtract
        """
        all_extracts = []

        # すべてのtaggerのパターンの正規表現を順に適用していく
        for type_name, patterns in self.all_patterns.items():
            for pattern in patterns:
                # 文字列中からのパターン検知
                re_iter = re.finditer(pattern.re_pattern, processed_text)
                for re_match in re_iter:
                    all_extracts.append(Extract(type_name=type_name, re_match=re_match, pattern=pattern))
        return all_extracts

    def _extract_filter(self, extracts: List[Extract], processed_text: str) -> List[Extract]:
        """候補Extractの中から必要なものだけをフィルタリングする

        Args:
            extracts (List[Extract]): 候補となるExtractのリスト
            processed_text (str): 入力文字列

        Returns:
            List[Extract]: フィルタされたExtractのリスト
        """
        results = []
        for extract in extracts:
            allow_append = True
            for pattern_filter in self.pattern_filters:
                if pattern_filter.filter(extract, processed_text):
                    allow_append = False
            if allow_append:
                results.append(extract)

        return results

    def _drop_duplicates(self, all_extracts: List[Extract], processed_text: str) -> DefaultDict[str, List[Extract]]:
        """候補Extractの中から、文字列上の同一箇所から重複して取得してしまった候補を除外する

        Args:
            all_extracts (List[Extract]): 候補となるExtractのリスト
            processed_text (str): 入力文字列

        Returns:
            DefaultDict[str, List[Extract]]: 重複除去されたExtractのリスト
        """
        type2extracts = defaultdict(list)
        text_coverage_flag = [False] * len(processed_text)

        # 開始位置の小さい順 → 文字列の長い順 → type_nameの降順(abstime→duration→reltime→set)
        ordered_extracts = sorted(
            all_extracts, key=lambda x: (x.re_match.span()[0], -len(x.re_match.group()), x.type_name)
        )
        for target_extract in ordered_extracts:
            start_i, end_i = target_extract.re_match.span()

            # すべてがまだ未使用のcharだった場合に候補に加える
            if any(text_coverage_flag[start_i:end_i]) is False:
                text_coverage_flag[start_i:end_i] = [True] * (end_i - start_i)
                type2extracts[target_extract.type_name].append(target_extract)

        return type2extracts

    def _parse(self, type2extracts: DefaultDict[str, List[Extract]]) -> List[TIMEX]:
        """抽出されたExtractをパースしてTIMEXに変換する

        Args:
            type2extracts (DefaultDict[str, List[Extract]]): タイプごとのExtractのリスト

        Returns:
            List[TIMEX]: パースされたTIMEXのリスト
        """
        results = []
        for type_name, extracts in type2extracts.items():
            for extract in extracts:
                if type_name == "abstime":
                    results.append(self.abstime_tagger.parse_with_pattern(extract.re_match, extract.pattern))
                elif type_name == "duration":
                    results.append(self.duration_tagger.parse_with_pattern(extract.re_match, extract.pattern))
                elif type_name == "reltime":
                    results.append(self.reltime_tagger.parse_with_pattern(extract.re_match, extract.pattern))
                elif type_name == "set":
                    results.append(self.set_tagger.parse_with_pattern(extract.re_match, extract.pattern))
                elif type_name == "custom":
                    results.append(self.custom_tagger.parse_with_pattern(extract.re_match, extract.pattern))

        return results

    def _modify_renge_start_and_end(self, timex_tags: List[TIMEX], processed_text: str) -> List[TIMEX]:
        """TIMEXタグに@rangeStartと@rangeEndを付与する

        Args:
            timex_tags (List[TIMEX]): TIMEXのリスト
            processed_text (str): 入力文字列

        Returns:
            List[TIMEX]: 情報が付与されたTIMEXのリスト
        """
        index2timex_i = {}
        for timex_i, timex in enumerate(timex_tags):
            if not timex.span:
                continue
            for index in range(timex.span[0], timex.span[1]):
                index2timex_i[index] = timex_i

        for timex in timex_tags:
            if not timex.span or timex.type == "DURATION":
                continue

            range_expression = detect_range_expression_before_timex(timex.span[0], processed_text)
            if not range_expression:
                continue

            possible_timex_end_i = timex.span[0] - len(range_expression) - 1
            possible_timex_i = index2timex_i.get(possible_timex_end_i)
            if possible_timex_i is not None:
                start_timex = timex_tags[possible_timex_i]

                if start_timex.type == timex.type:
                    start_timex.range_start = True
                    timex.range_end = True

        return timex_tags

    def _extract_abbrev_patten(self, timex_tags: List[TIMEX], processed_text: str) -> List[TIMEX]:
        """日付や時間の単位が省略されているものを取得する

        `1,2ヶ月`, `1~2分`, `2から3日`などの表現に対応するため
        - 注意：self._modify_renge_start_and_end()より後に実行する

        Args:
            timex_tags (List[TIMEX]): TIMEXのリスト
            processed_text (str): 入力文字列

        Returns:
            List[TIMEX]: 省略されたTIMEXを加えたリスト(ソートされていない)
        """
        additional_timexes = []
        for timex in timex_tags:
            if not timex.span:
                continue

            range_expression = detect_range_expression_before_timex(
                timex.span[0], processed_text, range_expressions=["〜", "~", "-", "から", ",", "、"]
            )
            if not range_expression:
                continue

            possible_timex_end_i = timex.span[0] - len(range_expression) - 1
            re_match_num = re.search(r"[0-9\.:：/]+$", processed_text[: possible_timex_end_i + 1])
            if re_match_num:
                re_abbrev_suffix = re.search(r"([0-9\.]+)(.+)", timex.text)
                if not re_abbrev_suffix or not timex.pattern:
                    continue
                abbrev_suffix = re_abbrev_suffix.group(2)
                abbrev_text_origin = re_match_num.group(0)

                abbrev_full_text = abbrev_text_origin + abbrev_suffix
                re_match = re.fullmatch(timex.pattern.re_pattern, abbrev_full_text)
                if re_match:
                    abbrev_timex = timex.pattern.parse_func(re_match, timex.pattern)
                    # 元のテキストや対応するTIMEXに合わせて変更する
                    # modとquantは、すでにtimex.patternの中に含まれているので明示的に変更する必要がない
                    abbrev_timex.text = abbrev_text_origin
                    abbrev_timex.span = re_match_num.span()
                    additional_timexes.append(abbrev_timex)

        return timex_tags + additional_timexes

    def _modify_additional_information(self, timex_tags: List[TIMEX]) -> List[TIMEX]:
        """TIMEXタグに追加の情報を付与する

        付与される情報
        - @tid: ドキュメントに対して抽出されたTIMEXの通し番号
        - reference: 基準日時 (TimexParser.referenceに指定されていた場合)

        Args:
            timex_tags (List[TIMEX]): TIMEXのリスト

        Returns:
            List[TIMEX]: 情報が付与されたTIMEXのリスト
        """
        # update @tid and reference
        modified_tags = []
        sorted_timex_tags = sorted(timex_tags, key=lambda x: x.span[0] if x.span else 0)
        for i, timex in enumerate(sorted_timex_tags):
            timex.tid = f"t{i}"
            if self.reference:
                timex.reference = self.reference
            modified_tags.append(timex)

        return modified_tags
