import pandas as pd
import streamlit as st

from ja_timex.timex import TimexParser


def export_as_tagged_text(timexes, text):
    for timex in sorted(timexes, key=lambda x: x.span[0], reverse=True):
        # streamlit上で分かりやすいように、タグの前後を改行する
        text = text[: timex.span[0]] + "\n" + timex.to_tag() + "\n" + text[timex.span[1] :]
    return text


text = st.text_area("Text to analyze", "")


timex_parser = TimexParser()


if text:
    text = text.replace("\n", "").strip()
    timexes = timex_parser.parse(text)

    if timexes is None:
        st.write("No Result")
    else:
        st.code(export_as_tagged_text(timexes, text), language="xml")

        for timex in timexes:
            timex_df = pd.DataFrame(
                [
                    timex.tid,
                    timex.type,
                    timex.value,
                    timex.text,
                    timex.freq,
                    timex.quant,
                    timex.mod,
                    timex.parsed,
                    timex.value_format,
                    timex.span,
                ],
                index=[
                    "@tid",
                    "@type",
                    "@value",
                    "@text",
                    "@freq",
                    "@quant",
                    "@mod",
                    "@parsed",
                    "@value_format",
                    "@span",
                ],
                columns=["value"],
            )
            st.table(timex_df)
