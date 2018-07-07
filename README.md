### python-nyct-experiments

A repository for experiments with the live NYC MTA endpoints.

Some investigation being done in ipython notebooks. The first one is [MTA Subway Time Analysis 180630](./MTA Subway Time Analysis 180630.ipynb). Some information on dependencies and data sources also included there.

### nyct_viewer

A django application for consuming real-time MTA data and presenting it back to users over a web application. Essentially an automated version of the analysis prototyped in the ipython notebook.

Updated train information will be broadcast to all connected web clients using websockets.

## Dependencies

* python 3
* django >2
    * With channels, channels\_redis, 
* redis2.8, running on port 6379
    * (tested using docker [via these instructions](https://channels.readthedocs.io/en/latest/tutorial/part_2.html))

To use the django application, cd into the ```nyct_viewer/``` folder and execute
```
python3 manage.py runserver
```
in one terminal, and
```
python3 manage.py runworker scraper
```
in another terminal.

Then navigate to [localhost:8000/realtime_stream/](http://localhost:8000/realtime_stream/) to view realtime updates.
