cd /srv/dryrun/soweego/
/usr/bin/tmux kill-session -t pipeline-discogs
/usr/bin/tmux new-session -d -s "pipeline-discogs" ./scripts/docker/launch_pipeline.sh -c ../prod_cred.json -s /srv/dryrun/discogs-shared/ discogs --no-upload --validator
/usr/bin/tmux set remain-on-exit on -t pipeline-discogs
