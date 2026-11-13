def ngram(test_client, kind, **params) -> dict:
    response = test_client.post(f"/ngram_{kind}", json=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_totals_are_word_frequency_pairs_in_descending_order(test_client) -> None:
    totals = test_client.get("/totals/5").json()
    assert len(totals) == 5
    assert totals[0] == [".", 26521]
    assert [frequency for _, frequency in totals] == sorted((f for _, f in totals), reverse=True)


def test_totals_requires_a_number(test_client) -> None:
    assert test_client.get("/totals/many").status_code == 422


def test_ngram_book_is_keyed_by_word_and_year(test_client) -> None:
    result = ngram(test_client, "book", word=["Peer", "Nora"], period=[1880, 1950])
    assert result == {"Peer 1890": 4, "Peer 1940": 395, "Nora 1890": 686, "Nora 1893": 30}


def test_ngram_period_defaults_to_1950_1990(test_client) -> None:
    assert ngram(test_client, "book", word=["Peer"]) == {}


def test_ngram_accepts_a_single_word(test_client) -> None:
    assert ngram(test_client, "book", word="Peer", period=[1940, 1940]) == {"Peer 1940": 395}


def test_ngram_book_filters(test_client) -> None:
    params = {"word": ["og"], "period": [1800, 1950]}
    assert set(ngram(test_client, "book", **params, city="Oslo")) == {"og 1940"}
    assert set(ngram(test_client, "book", **params, lang="%nno%")) == {"og 1872", "og 1894"}
    assert set(ngram(test_client, "book", **params, publisher="gyldendal")) == {"og 1887", "og 1899", "og 1940"}
    assert set(ngram(test_client, "book", **params, title="peer%")) == {"og 1940"}
    assert set(ngram(test_client, "book", **params, topic="parodi")) == {"og 1893"}


def test_ngram_periodicals(test_client) -> None:
    result = ngram(test_client, "periodicals", word=["og"], period=[1800, 1950])
    assert result == {"og 1835": 38, "og 1870": 123, "og 1893": 295}
    assert set(ngram(test_client, "periodicals", word=["og"], period=[1800, 1950], ddk="133%")) == {"og 1893"}


def test_ngram_newspapers_per_year(test_client) -> None:
    result = ngram(test_client, "newspapers", word=["og"], period=[1800, 1950])
    assert result == {"og 1852": 439, "og 1870": 304, "og 1882": 238}


def test_ngram_newspapers_per_date(test_client) -> None:
    result = ngram(test_client, "newspapers", word=["og"], period=[18700101, 18821231])
    assert result == {"og 18700309": 304, "og 18820110": 238}


def test_ngram_newspapers_month_period_uses_first_day_of_month(test_client) -> None:
    """Legacy quirk: 187003-188201 means 18700301-18820101, which excludes the issue of 10 January 1882."""
    result = ngram(test_client, "newspapers", word=["og"], period=[187003, 188201])
    assert result == {"og 18700309": 304}


def test_ngram_newspapers_title_is_exact(test_client) -> None:
    result = ngram(test_client, "newspapers", word=["og"], period=[1800, 1950], title="VG (1868-1923) ")
    assert result == {"og 1870": 304}


def test_ngram_requires_words(test_client) -> None:
    assert test_client.post("/ngram_book", json={}).status_code == 422
