FROM python:2

ADD requirements.txt /
ADD hdf5_convert.py /
ADD csv_utils.py /

RUN pip install -r /requirements.txt --ignore-installed

ENTRYPOINT ["python", "hdf5_convert.py"]
