import pytest

from ja_timex.tag import TIMEX
from ja_timex.timex import TimexParser


@pytest.fixture(scope="module")
def p():
    return TimexParser()


def test_abstime(p):
    timexes = p.parse("2021年7月18日")
    assert len(timexes) == 1
    assert type(timexes[0]) == TIMEX
    assert timexes[0].value == "2021-07-18"

    timexes = p.parse("2021回目の7月18日")
    assert len(timexes) == 1
    assert type(timexes[0]) == TIMEX
    assert timexes[0].value == "XXXX-07-18"


def test_tid_is_modified_in_parsing(p):
    timexes = p.parse("彼は2008年4月から週に3回ジョギングを1時間行ってきた")

    assert timexes[0].tid == "t0"
    assert timexes[1].tid == "t1"
    assert timexes[2].tid == "t2"


def test_ignore_number_normalize(p):
    # 一を1と変換しない。可読性のために、reltimeのPatternでも漢数字で扱う
    timexes = p.parse("一昨年と一昨日は言うのに一昨月とは言わないのは何故か")

    assert timexes[0].value == "P2Y"
    assert timexes[1].value == "P2D"

    timexes = p.parse("一昨昨日と一昨々日")
    assert len(timexes) == 2
    assert timexes[0].value == "P3D"
    assert timexes[1].value == "P3D"


def test_every_year_and_month(p):
    timexes = p.parse("毎年6月から8月にかけて")

    assert len(timexes) == 3
    assert timexes[0].value == "P1Y"
    assert timexes[0].type == "SET"
    assert timexes[1].value == "XXXX-06-XX"
    assert timexes[1].type == "DATE"
    assert timexes[2].value == "XXXX-08-XX"
    assert timexes[2].type == "DATE"


def test_morning_evening(p):
    timexes = TimexParser().parse("朝9時スタートです。")
    assert len(timexes) == 1
    assert timexes[0].value == "T09-XX-XX"
    assert timexes[0].type == "TIME"
    assert timexes[0].text == "朝9時"

    timexes = TimexParser().parse("今夜9時スタートです。")
    assert len(timexes) == 1
    assert timexes[0].value == "T21-XX-XX"
    assert timexes[0].type == "TIME"
    assert timexes[0].text == "今夜9時"


def test_duration_with_half_expression(p):
    timexes = TimexParser().parse("今から1時間半後に始めます")
    assert len(timexes) == 1
    assert timexes[0].value == "PT1.5H"
    assert timexes[0].type == "DURATION"
    assert timexes[0].text == "1時間半後"

    timexes = TimexParser().parse("今から2年半ほど前の話")
    assert len(timexes) == 1
    assert timexes[0].value == "P2.5Y"
    assert timexes[0].type == "DURATION"
    assert timexes[0].text == "2年半ほど前"


def test_duration_with_half_expression_without_number(p):
    timexes = TimexParser().parse("半年前の記念日")
    assert len(timexes) == 1
    assert timexes[0].value == "P0.5Y"
    assert timexes[0].type == "DURATION"
    assert timexes[0].text == "半年前"

    timexes = TimexParser().parse("四半世紀の時を経て")
    assert len(timexes) == 1
    assert timexes[0].value == "P25Y"
    assert timexes[0].type == "DURATION"
    assert timexes[0].text == "四半世紀"


def test_just_suffix_reltime(p):
    # 8日というDATEではなく、8日目というDURATION
    timexes = p.parse("8日目の蝉")
    assert timexes[0].value == "P8D"
    assert timexes[0].type == "DURATION"
    assert timexes[0].mod is None
    assert timexes[0].text == "8日目"

    timexes = p.parse("30年もの間")
    assert timexes[0].value == "P30Y"
    assert timexes[0].type == "DURATION"
    assert timexes[0].mod is None
    assert timexes[0].text == "30年もの間"

    timexes = p.parse("15年ぶりに再会した")
    assert timexes[0].value == "P15Y"
    assert timexes[0].type == "DURATION"
    assert timexes[0].mod is None
    assert timexes[0].text == "15年ぶり"


def test_ampm_suffix_with_space(p):
    timexes = p.parse("18:00　（予定）")
    assert timexes[0].value == "T18-00-XX"
    assert timexes[0].text == "18:00"


def test_ambiguous_phrase(p):
    timexes = p.parse("翌週28日")

    # "週28日"ではなく、"翌週","28日"と取得される
    assert timexes[0].value == "P1W"
    assert timexes[0].text == "翌週"
    assert timexes[1].value == "XXXX-XX-28"
    assert timexes[1].text == "28日"

    # DATEの28日とDURATIONの28日があるがabsdateの方が優先される
    timexes = p.parse("28日")
    assert timexes[0].value == "XXXX-XX-28"
    assert timexes[0].type == "DATE"
    assert timexes[0].text == "28日"


def test_decimal_duration(p):
    # DURATIONはDecimalFilterの対象外
    timexes = p.parse("0.5日間")
    assert timexes[0].value == "P0.5D"
    assert timexes[0].text == "0.5日間"
    assert timexes[0].type == "DURATION"

    # 0.5だけだと0年5月とDATE判定(abstime)されるため、DecimalFilterで除外
    assert len(p.parse("0.5")) == 0


def test_range_expression_pattern(p):
    timexes = p.parse("1901年〜2000年")
    assert timexes[0].range_start
    assert timexes[0].range_end is None
    assert timexes[1].range_start is None
    assert timexes[1].range_end
    assert timexes[0].type == "DATE"
    assert timexes[1].type == "DATE"
    assert timexes[0].text == "1901年"
    assert timexes[1].text == "2000年"

    timexes = p.parse("4月から5月にかけて")
    assert timexes[0].range_start
    assert timexes[0].range_end is None
    assert timexes[1].range_start is None
    assert timexes[1].range_end
    assert timexes[0].type == "DATE"
    assert timexes[1].type == "DATE"
    assert timexes[0].text == "4月"
    assert timexes[1].text == "5月"

    timexes = p.parse("1時~2時の間")
    assert timexes[0].range_start
    assert timexes[0].range_end is None
    assert timexes[1].range_start is None
    assert timexes[1].range_end
    assert timexes[0].type == "TIME"
    assert timexes[1].type == "TIME"
    assert timexes[0].text == "1時"
    assert timexes[1].text == "2時"

    timexes = p.parse("10日-20日")
    assert timexes[0].range_start
    assert timexes[0].range_end is None
    assert timexes[1].range_start is None
    assert timexes[1].range_end
    assert timexes[0].type == "DATE"
    assert timexes[1].type == "DATE"
    assert timexes[0].text == "10日"
    assert timexes[1].text == "20日"


def test_range_expression_invalid(p):
    # 範囲表現が入っているものの、範囲の開始と終了を表すわけではない場合

    # 「2008年4月」と「週に3回」は、「から」に挟まれているが範囲指定ではない
    assert p.parse("彼は2008年4月から週に3回ジョギングを1時間行ってきた")[0].range_start is None
    assert p.parse("彼は2008年4月から週に3回ジョギングを1時間行ってきた")[1].range_end is None

    assert p.parse("この4月から3ヶ月間の研修が始まる")[0].range_start is None
    assert p.parse("この4月から3ヶ月間の研修が始まる")[1].range_end is None

    assert p.parse("今月から1日も休みがない")[0].range_start is None
    assert p.parse("今月から1日も休みがない")[1].range_end is None

    assert p.parse("今週から3日間も雨が降り続いている")[0].range_start is None
    assert p.parse("今週から3日間も雨が降り続いている")[1].range_end is None


def test_extract_abbrev_patten(p):
    # 範囲と似た表現ではあるが、範囲を表すわけではないので@rangeStartや@rangeEndは付与しない

    # DURATION
    for text in ["1~2日間", "1〜2日間", "1、2日間", "1,2日間", "1から2日間"]:
        timexes = p.parse(text)
        assert timexes[0].range_start is None
        assert timexes[0].range_end is None
        assert timexes[1].range_start is None
        assert timexes[1].range_end is None

        assert timexes[0].type == "DURATION"  # typeを補完する
        assert timexes[1].type == "DURATION"

        assert timexes[0].text == "1"  # textで省略されている"間"は補完しない
        assert timexes[1].text == "2日間"

    # DATE
    for text in ["1~2日", "1〜2日", "1、2日", "1,2日", "1から2日"]:
        timexes = p.parse(text)
        assert timexes[0].range_start is None
        assert timexes[0].range_end is None
        assert timexes[1].range_start is None
        assert timexes[1].range_end is None

        assert timexes[0].type == "DATE"  # typeを補完する
        assert timexes[1].type == "DATE"

        assert timexes[0].text == "1"
        assert timexes[1].text == "2日"

    # TIME
    for text in ["1~2分", "1〜2分", "1、2分", "1,2分", "1から2分"]:
        timexes = p.parse(text)
        assert timexes[0].range_start is None
        assert timexes[0].range_end is None
        assert timexes[1].range_start is None
        assert timexes[1].range_end is None

        assert timexes[0].type == "TIME"  # typeを補完する
        assert timexes[1].type == "TIME"

        assert timexes[0].text == "1"
        assert timexes[1].text == "2分"


def test_range_expression_mod(p):
    # @modがある場合
    timexes = p.parse("1から2日前")
    assert timexes[0].range_start is None
    assert timexes[0].range_end is None
    assert timexes[1].range_start is None
    assert timexes[1].range_end is None

    assert timexes[0].type == "DURATION"  # typeを補完する
    assert timexes[1].type == "DURATION"

    assert timexes[0].mod == "BEFORE"  # modを補完する
    assert timexes[1].mod == "BEFORE"

    assert timexes[0].text == "1"
    assert timexes[1].text == "2日前"


def test_range_expression_qunat(p):
    # @quantがある場合
    timexes = p.parse("1から2日おきに")
    assert timexes[0].range_start is None
    assert timexes[0].range_end is None
    assert timexes[1].range_start is None
    assert timexes[1].range_end is None

    assert timexes[0].type == "SET"  # typeを補完する
    assert timexes[1].type == "SET"

    assert timexes[0].quant == "EVERY"  # quantを補完する
    assert timexes[1].quant == "EVERY"

    assert timexes[0].text == "1"
    assert timexes[1].text == "2日おき"


def test_range_expression_digit(p):
    for text in ["1.5~2.5日間", "1.5〜2.5日", "1.5,2.5分"]:
        timexes = p.parse(text)
        assert timexes[0].range_start is None
        assert timexes[0].range_end is None
        assert timexes[1].range_start is None
        assert timexes[1].range_end is None

        assert timexes[0].text == "1.5"
        assert timexes[1].text.startswith("2.5")


def test_range_expression_time(p):
    # 範囲表現のうち、数字表現に:や/を含むもの
    timexes = p.parse("12:00〜17:30")
    assert len(timexes) == 2
    assert timexes[0].text == "12:00"
    assert timexes[1].text == "17:30"

    timexes = p.parse("12：00〜17：30")
    assert len(timexes) == 2
    assert timexes[0].text == "12：00"
    assert timexes[1].text == "17：30"

    timexes = p.parse("2/1〜2/14発売")
    assert len(timexes) == 2
    assert timexes[0].text == "2/1"
    assert timexes[1].text == "2/14"


def test_range_expression_variation(p):
    # 範囲表現のうち、"Aから翌B", "Aから同B"という表現
    timexes = p.parse("2005年11月から翌2006年7月")
    assert len(timexes) == 2
    assert timexes[0].text == "2005年11月"
    assert timexes[0].range_start
    assert timexes[1].text == "2006年7月"
    assert timexes[1].range_end

    timexes = p.parse("午後1時半から同3時半")
    assert len(timexes) == 2
    assert timexes[0].text == "午後1時半"
    assert timexes[0].range_start
    assert timexes[1].text == "3時半"
    assert timexes[1].range_end

    # 範囲ではない場合（DURATIONは範囲表現を取らない）
    timexes = p.parse("1日から翌日のことが気になって仕方がない")
    assert timexes[0].text == "1日"
    assert timexes[0].type == "DATE"
    assert timexes[0].range_start is None
    assert timexes[1].text == "翌日"
    assert timexes[1].type == "DURATION"
    assert timexes[1].range_end is None
