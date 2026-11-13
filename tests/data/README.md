# Testdatabase

This test database follows the same structure as our internal database, but it contains only data from documents in the public domain.
It is manually constructed with a couple of edge cases in mind:

1. The code should work with multiple shards
2. The code should work with different document types
3. The code should work with different languages (for books)
4. The number of documents in each shard should not matter

The database is therefore set up the following way:

1. There are three shards with only books, one contains only a single language (which is only in this shard) and two with multiple languages, where one of the languages overlap between shards
2. There are two shards for newspapers, one shard with two newspapers and one with only one newspaper
3. There is one shard with multiple periodicals

URNs for all books are validated as being in the public domain on 2026-05-11.

Every document is listed below with its dhlabid, the identifier used by the API, followed by its URN.

The following books are part of the database:

- 100000008: URN:NBN:no-nb_digibok_2010083012002 (Ibsen Kalender, 1900 edition)
- 100000004: URN:NBN:no-nb_digibok_2017020148047 (Peer Gynt, 1940 edition)
- 100000001: URN:NBN:no-nb_digibok_2017010448142 (Punch's lomme-Ibsen: fire parodier, 1893 edition)
- 100000005: URN:NBN:no-nb_digibok_2016042108294 (Edvard Munch : et foredrag holdt i anledning af en udstilling af kunstnerens arbeider i Kristiania, 1907 edition)
- 100000003: URN:NBN:no-nb_digibok_2014102708091 (Sankt Hans Fest : Fortælling, 1887 edition)
- 100000000: URN:NBN:no-nb_digibok_2010090120024 (A doll's house, and other plays, 1890 edition)
- 100000002: URN:NBN:no-nb_digibok_2008040304027 (Kærlighedens komedie : komedie i tre akter, 1899 edition)
- 100000006: URN:NBN:no-nb_digibok_2016101448019 (Billedbog : Barnevers med billeder, 1894 edition)
- 100000007: URN:NBN:no-nb_digibok_2014102438023 (Saga um Gunnlaug Ormstunga, 1872 edition)

The following newspapers are part of the database:

- 200000001: URN:NBN:no-nb_digavis_christianiaposten_null_null_18521017_2_1473_1
- 200000000: URN:NBN:no-nb_digavis_nordmandenosloattenaattito_null_null_18820110_5_8_1
- 200000002: URN:NBN:no-nb_digavis_verdensgang_null_null_18700309_3_10_1

The following periodicals are part of the database:

- 300000000: URN:NBN:no-nb_digitidsskrift_2025082580005_020
- 300000001: URN:NBN:no-nb_digitidsskrift_2025090280001_034
- 300000002: URN:NBN:no-nb_digitidsskrift_2024010980033_013

## Documents per shard

Each `alto_<from>_<to>.db` file holds the documents with dhlabids in the range given by its name. The first digit of
a dhlabid gives the document type: 1 is books (`digibok`), 2 is newspapers (`digavis`) and 3 is periodicals
(`digitidsskrift`).

| Shard file | dhlabid | Year | Title |
|---|---|---|---|
| `alto_100000000_100000000.db` | 100000000 | 1890 | A doll's house, and other plays |
| `alto_100000001_100000004.db` | 100000001 | 1893 | Punch's lomme-Ibsen : fire parodier |
|  | 100000002 | 1899 | Kærlighedens komedie : komedie i tre akter |
|  | 100000003 | 1887 | Sankt Hans Fest : Fortælling |
|  | 100000004 | 1940 | Peer Gynt |
| `alto_100000005_100000008.db` | 100000005 | 1907 | Edvard Munch : et foredrag holdt i anledning af en udstilling af kunstnerens arbeider i Kristiania |
|  | 100000006 | 1894 | Billedbog : Barnevers med billeder |
|  | 100000007 | 1872 | Saga um Gunnlaug Ormstunga |
|  | 100000008 | 1900 | Ibsen-kalender |
| `alto_200000000_200000001.db` | 200000000 | 1882 | Nordmanden (Oslo: 1882-1883) |
|  | 200000001 | 1852 | Christiania-Posten |
| `alto_200000002_200000002.db` | 200000002 | 1870 | VG (1868-1923) |
| `alto_300000000_300000002.db` | 300000000 | 1893 | Morgendemringen. 1893 Vol. 8 Nr. 8 |
|  | 300000001 | 1870 | Almuevennen : et Ugeblad til Oplysnings Fremme blandt Menigmand. 1870 Vol. 22 Nr. 34 |
|  | 300000002 | 1835 | Flyvebladet (Trondhjem). 1835 Nr. 13 |

`urns.db` and `metadata.db` have one row for each of the 15 documents. `grand_total.db` holds word totals summed over
the shards.

We are using the following code to create the database: https://github.com/NationalLibraryOfNorway/dhlab-nb-fulltext-index/
