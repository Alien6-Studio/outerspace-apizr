from fastapi import FastAPI
from pydantic import BaseModel


from typing import Tuple, List


import main as main

app = FastAPI()


class Hello_model(BaseModel):
   test: str

@app.post('/hello')
def hello_service( arguments: Hello_model):
    try:
        return main.hello(test = arguments.test)
    except Exception as err:
      return {"errors": "an exception was thrown during program execution"}, 500

class Addition_model(BaseModel):
   a: int
   b: int

@app.post('/addition')
def addition_service( arguments: Addition_model):
    try:
        return main.addition(a = arguments.a, b = arguments.b)
    except Exception as err:
      return {"errors": "an exception was thrown during program execution"}, 500

class Testtuple_model(BaseModel):
   a: [int, str]

@app.post('/testtuple')
def testtuple_service( arguments: Testtuple_model):
    try:
        return main.testtuple(a = arguments.a)
    except Exception as err:
      return {"errors": "an exception was thrown during program execution"}, 500

class Testlist_model(BaseModel):
   a: [str]

@app.post('/testList')
def testList_service( arguments: Testlist_model):
    try:
        return main.testList(a = arguments.a)
    except Exception as err:
      return {"errors": "an exception was thrown during program execution"}, 500
