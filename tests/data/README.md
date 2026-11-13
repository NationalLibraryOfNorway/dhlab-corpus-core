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

The following books are part of the database:

- URN:NBN:no-nb_digibok_2010083012002 (Ibsen Kalender, 1900 edition)
- URN:NBN:no-nb_digibok_2017020148047 (Peer Gynt, 1940 edition)
- URN:NBN:no-nb_digibok_2017010448142 (Punch's lomme-Ibsen: fire parodier, 1893 edition)
- URN:NBN:no-nb_digibok_2016042108294 (Edvard Munch : et foredrag holdt i anledning af en udstilling af kunstnerens arbeider i Kristiania, 1907 edition)
- URN:NBN:no-nb_digibok_2014102708091 (Sankt Hans Fest : Fortælling, 1887 edition)
- URN:NBN:no-nb_digibok_2010090120024 (A doll's house, and other plays, 1890 edition)
- URN:NBN:no-nb_digibok_2008040304027 (Kærlighedens komedie : komedie i tre akter, 1899 edition)
- URN:NBN:no-nb_digibok_2016101448019 (Billedbog : Barnevers med billeder, 1894 edition)
- URN:NBN:no-nb_digibok_2014102438023 (Saga um Gunnlaug Ormstunga, 1872 edition)

The following newspapers are part of the database:

- URN:NBN:no-nb_digavis_christianiaposten_null_null_18521017_2_1473_1
- URN:NBN:no-nb_digavis_nordmandenosloattenaattito_null_null_18820110_5_8_1
- URN:NBN:no-nb_digavis_verdensgang_null_null_18700309_3_10_1

The following periodicals are part of the database:

- URN:NBN:no-nb_digitidsskrift_2025082580005_020
- URN:NBN:no-nb_digitidsskrift_2025090280001_034
- URN:NBN:no-nb_digitidsskrift_2024010980033_013

We are using the following code to create the database: https://github.com/NationalLibraryOfNorway/dhlab-nb-fulltext-index/
