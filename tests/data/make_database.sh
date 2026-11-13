#!/bin/bash
rm -rf db

mkdir -p tempstore db

container_image=$1

for shard in ./ocr_data/*
do
    docker run \
        -v $shard:/data:ro \
        -v ./tempstore/:/tempstore \
        -v ./db/:/db \
        $container_image \
        python src/ft_index/pipeline.py --alto_dir_path /data --cache_dir_path /tempstore --db_dir_path /db
done

rm -rf tempstore

# Word totals for the whole collection, summed over the shards
python ../../scripts/make_grand_total.py db
