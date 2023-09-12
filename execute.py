
import copy
import datetime as dt
import os
import random
import time

import numpy as np
import pandas as pd
#from google_sheets.google_sheets import GoogleSheets
from backtest import StrategyConfig
from config import (apply_filter, broker, end_time, execute, start_time,
                    strategies, tickers, trades_url, open_trades_name)
from degiro import (DataType, DeGiro, IntervalType, Order, Product,
                    ResolutionType)
from indicators import Indicators
from signals import Signals


class Trade:

    def __init__(self, data:pd.DataFrame=None, signal:str=None, strategy:StrategyConfig=None,
                 balance:float=None) -> None:

        '''
        Generates the trade object for the backtest.

        Parameters
        ----------
        candle: dict
            Dictionary with the current candle data.
        signal: str
            Direction for the trade. It can be 'long' or 'short'.
        strategy: str
            Name of the strategy used to enter the trade.
        entry: float
            Entry price.
        balance: float
            Balance when entering the trade.
        '''
        
        self.entrytime =  dt.datetime.today().strftime('%Y-%m-%d %H:%M')
        self.exittime = None
        self.exit = None
        self.returns = None
        self.balance = balance
        self.signal = signal
        self.result = None

        if isinstance(data,pd.DataFrame):
            candle = data.iloc[-1]
            self.candle = candle
            self.datetime = candle['DateTime']
            self.ticker = candle['Ticker']
            self.entry = self.calculateEntry(candle, data.iloc[-2])
        else:
            self.ticker = None
            self.entry = None

        if strategy != None:
            strategy = copy.deepcopy(strategy)
            self.strategy = strategy

            asset = copy.deepcopy(strategy.assets[candle['Ticker']])
            self.asset = asset
            self.order = asset.order_type
            self.risk = asset.risk
            if self.ticker == None:
                self.ticker = asset.name

            sldist = asset.sl * candle['distATR']
            tpdist = asset.tp * candle['distATR']
            self.sldist = sldist
        else:
            self.asset = None

        if data != None and strategy != None:
            self.sl = self.entry - sldist if signal == 'long' else self.entry + sldist
            self.tp = self.entry + tpdist if signal == 'long' else self.entry - tpdist

        self.size = self.calculateSize()

    def calculateEntry(self, candle:dict=None, prev_candle:dict=None) -> float:

        if candle == None or prev_candle == None:
            raise ValueError('Candle data is needed for the Entry to be calculated')
        
        entry = candle['Open']
        if self.signal == 'long':
            if self.order == 'stop':
                if 'High' in prev_candle[candle['Ticker']] and \
                    prev_candle[candle['Ticker']]['High'] > candle['Open']:
                    entry = prev_candle[candle['Ticker']]['High']
                else:
                    self.order = 'market'
            elif self.order == 'limit':
                if 'Low' in prev_candle[candle['Ticker']] and \
                    prev_candle[candle['Ticker']]['Low'] < candle['Open']:
                    entry = prev_candle[candle['Ticker']]['Low']
                else:
                    self.order = 'market'
        elif self.signal == 'short':
            if self.order == 'stop':
                if 'Low' in prev_candle[candle['Ticker']] and \
                    prev_candle[candle['Ticker']]['Low'] < candle['Open']:
                    entry = prev_candle[candle['Ticker']]['Low']
                else:
                    self.order = 'market'
            elif self.order == 'limit':
                if 'High' in prev_candle[candle['Ticker']] and \
                    prev_candle[candle['Ticker']]['High'] > candle['Open']:
                    entry = prev_candle[candle['Ticker']]['High']
                else:
                    self.order = 'market'

        return entry

    def calculateSize(self, risk:float=None, balance:float=None, 
                      sldist:float=None) -> float:

        '''
        Calculates the size of the trade.

        Returns
        -------
        size: float
            Size of the trade.
        '''
        
        if risk != None:
            self.risk = risk
        if balance != None:
            self.balance = balance
        if sldist != None:
            self.sldist = sldist
        if risk == None and balance == None and sldist == None and self.asset == None:
            raise ValueError('There is not enough data to calculate the \
                             trade size. An asset should be specified for the trade.')

        self.size = int(self.risk * self.balance / self.sldist)
        if self.size > self.asset.max_size:
            self.size = self.asset.max_size
        elif self.size < self.asset.min_size:
            self.size = self.asset.min_size
        
        if self.size * self.entry > self.balance:
            self.size = int(self.balance/self.entry)

        if self.balance <= 0:
            self.size = 0.0

        return self.size

    def exitTrade(self, exit:float) -> None:

        '''
        Calculates the Exit variables.

        Parameters
        ----------
        exit: float
            Exit price.
        '''

        self.exittime = dt.datetime.today().strftime('%Y-%m-%d %H:%M')
        self.exit = exit
        self.returns = exit - self.entry if self.signal == 'long' else self.entry - exit
    
    def to_dict(self):

        '''
        Generates a dictionary with the trade data.

        Returns
        -------
        object: dict
            Contains the data.
        '''

        self.exitTrade()

        return self.__dict__

class TradesFiles:

    def __init__(self, path:str='execution') -> None:
        self.path = path

    def getOpenTrades(self, file:str='open_trades.csv') -> pd.DataFrame:

        if '.csv' in file:
            trades = pd.read_csv(file)
        elif '.xlsx' in file:
            trades = pd.read_excel(file)

        return trades
    
    def addOpenTrades(self, data:pd.DataFrame, file:str='open_trades.csv', mode:str='a') -> None:

        path = os.path.join(self.path, 'open_trades.csv')
        exists = os.path.exists(path)
        if '.csv' in file:
            data.to_csv(path, mode=mode, index=False, header=False if exists else True)
        elif '.xlsx' in file:
            with pd.ExcelWriter(path, mode=mode) as writer:
                df.to_excel(writer, index=False, header=False if exists else True)

    def deleteOpenTrade(self, data:pd.DataFrame, file:str='open_trades.csv') -> None:

        old_data = self.getOpenTrades(file=file)
        new_data = []
        for d in old_data.to_dict('records'):
            if d not in data.to_dict('records'):
                new_data.append(d)
        
        self.addOpenTrades(data=pd.DataFrame(new_data), file=file, mode='w')
    

    

def postOrder(trade:Trade=None, product_id:str=None, side:str=None, 
              order:str=None, entry:float=None, sl_dist:float=None,
              size:float=None) -> None:

    if trade != None:
        product_id = trade.asset.id
        side = trade.signal
        order = trade.order
        entry = trade.entry
        sl_dist = trade.sldist
        size = trade.size
    elif product_id == None or side == None or order == None or \
        entry == None or sl_dist == None or size == None:
        raise ValueError('Input a trade or some trade data.')
    
    product = dg.searchProducts(product_id)[0]
    side = 'BUY' if side == 'long' else 'SELL'
    
    limit = None
    if execute:

        if order == 'stoplimit':
            limit = entry + sl_dist/2 if side == 'BUY' \
                    else entry - sl_dist/2
            dg.tradeOrder(product, int(size), side, Order.Type.STOPLIMIT, 
                        Order.Time.GTC, limit=limit, stop_loss=entry)
            
        elif order == 'stop':
            dg.tradeOrder(product, int(size), side, Order.Type.STOPLOSS, 
                        Order.Time.GTC, stop_loss=entry)
            
        elif order == 'limit':
            dg.tradeOrder(product, int(size), side, Order.Type.LIMIT,
                        Order.Time.GTC, limit=entry)

        elif order == 'market':
            entry = dg.getQuote(product)['data']['lastPrice']
            limit = entry + sl_dist/2 if side == 'BUY' \
                    else entry - sl_dist/2
            dg.tradeOrder(product, int(size), side, Order.Type.STOPLIMIT, 
                        Order.Time.GTC, limit=limit, stop_loss=entry)
            
        else:
                dg.tradeOrder(product, int(size), side, Order.Type.MARKET, 
                            Order.Time.GTC)
                
    executions.append({'date':dt.datetime.today().strftime('%Y-%m-%d %H:%M'),
                       'product':product, 'size':int(size), 'side':side, 
                       'order':order, 'limit':limit, 'entry':entry})


def enterOrders(trades:dict) -> None:

    for symbol in trades:

        df = pd.DataFrame(trades[symbol])
        initial_size = df['size'].sum()
        df['size'] = np.where(df['signal'] == 'short', -df['size'], df['size'])

        total_size = df['size'].sum()
        if total_size > 0:
            side = 'long'
        elif total_size < 0:
            side = 'short'
        else:
            side = None

        if side != None:

            df = df[df['signal'] == side]
            df['size'] = np.where(df['signal'] == 'short', -df['size'], df['size'])
            for order in df.groupby('order'):

                size = order[1]['size'].sum()/initial_size * total_size 
                for entry in order['entry'].groupby('entry'):

                    # Check if there is enough balance 
                    balance = getEquity()
                    size = size if size*entry[0] <= balance else balance/entry[0]

                    # Prepare trade
                    trade = entry[1]['trade'].iloc[-1]
                    postOrder(product_id=symbol, side=side[0], order=order[0], 
                              entry=entry, sl_dist=trade.sldist, size=size)
                    
                    time.sleep(random.randint(40, 90))
        
def getEquity() -> float:

    return float(dg.getData(DataType.CASHFUNDS)[0][3:])

def getPortfolio() -> list:

    return dg.getData(DataType.PORTFOLIO)

def getQuote(product_id:str=None, product:Product=None):

    if product_id != None:
        product =  dg.searchProducts(product_id)[0]

    quote = dg.getQuote(product)['data']
    quote['tradingStartTime'] = dt.datetime.strptime(quote['tradingStartTime'], '%H:%M:%S').time()
    quote['tradingEndTime'] = dt.datetime.strptime(quote['tradingEndTime'], '%H:%M:%S').time()
    
    return quote

def time_interval(start:dt.time, end:dt.time, seconds:bool=True):

    reverse = False
    if start > end:
        start, end = end, start
        reverse = True

    delta = (end.hour - start.hour)*60 + end.minute - start.minute + (end.second - start.second)/60.0
    if reverse:
        delta = 24*60 - delta

    return delta * 60 if seconds else delta


def getData(strategies:dict, get_portfolio:bool=True):

    data = {}
    portfolio = {}
    for strat in strategies:

        # Prepare signal if exists
        if strat not in dir(signals):
            print(f'{strat} not between the defined signals.')
            continue
        signal = getattr(signals, strat)

        for s,c in strategies[strat].assets.items():
            
            strategies[strat].assets[s].id = tickers[s][broker]
            t = tickers[s][broker]
            
            # Get data
            if t not in data:
                product = dg.searchProducts(t)[0]

                # Check if market is open for the asset
                quote = getQuote(product=product)
                if dt.datetime.today().time() < quote['tradingStartTime'] or quote['tradingEndTime'] < dt.datetime.today().time():
                    data[t] = pd.DataFrame()
                    continue
                temp = dg.getCandles(Product(product).id, resolution=ResolutionType.H1, 
                                    interval=IntervalType.Y3)
            else:
                temp = data[t].copy()

            # Add columns
            temp['distATR'] = indicators.atr(n=20, method='s', dataname='ATR', new_df=temp)['ATR']
            temp['SLdist'] = temp['distATR'] * c.sl
            temp['Ticker'] = [s]*len(temp)
            temp['Date'] = pd.to_datetime(temp.index)
            if 'DateTime' not in temp.columns and 'Date' in temp.columns:
                temp.rename(columns={'Date':'DateTime'}, inplace=True)
            
            if 'Volume' not in temp.columns:
                temp['Volume'] = [0]*len(temp)
            
            # Calculate signal and apply filter
            temp = signal(df=temp, strat_name=strat)
            if apply_filter and strategies[strat].filter != None and 'MA' in strategies[strat].filter:
                period = int(strategies[strat].filter.split('_')[-1])
                temp['filter'] = temp['Close'].rolling(period).mean()
                temp[temp.columns[-2]] = np.where(temp['Close'] > temp['filter'], temp[temp.columns[-2]], 0)


            # Data treatment
            temp.sort_values('DateTime', inplace=True)
            temp['DateTime'] = pd.to_datetime(temp['DateTime'], unit='s')
            if temp['DateTime'].iloc[0].tzinfo != None:
                temp['DateTime'] = temp['DateTime'].dt.tz_convert(None)
            temp['Close'] = temp['Close'].fillna(method='ffill')
            temp['Spread'] = temp['Spread'].fillna(method='ffill')
            temp['Open'] = np.where(temp['Open'] != temp['Open'], temp['Close'], temp['Open'])
            temp['High'] = np.where(temp['High'] != temp['High'], temp['Close'], temp['High'])
            temp['Low'] = np.where(temp['Low'] != temp['Low'], temp['Close'], temp['Low'])

            # Store data
            if t in data:
                for c in temp:
                    if c not in data[t]:
                        data[t][c] = temp[c]
            else:
                data[t] = temp.copy()

            if portfolio:
                # Store portfolio
                if t not in portfolio:
                    portfolio[t] = []
            
                if temp.iloc[-1][f'{strat}Entry'] > 0:
                    trade = Trade(data=temp, signal='long', strategy=strategies[strat], 
                                balance=getEquity())
                    portfolio[t].append({**trade.to_dict(), **{'trade':trade}})

    if get_portfolio:
        return data, portfolio
    else:
        return data


if __name__ == '__main__':

    dg = DeGiro('OneMade','Onemade3680')
    signals = Signals(backtest=True, side=Signals.Side.LONG, errors=False, verbose=False)
    indicators = Indicators(errors=False)
    files = TradesFiles(path=trades_url)
    executions = []


    # Prepare data needed for backtest
    data, portfolio = getData(strategies, get_portfolio=True)

    # Execute orders
    for symbol in portfolio:

        df = pd.DataFrame(portfolio[symbol])
        initial_size = df['size'].sum()
        df['size'] = np.where(df['signal'] == 'short', -df['size'], df['size'])

        total_size = df['size'].sum()
        if total_size > 0:
            side = 'long'
        elif total_size < 0:
            side = 'short'
        else:
            side = None

        if side != None:

            df = df[df['signal'] == side]
            df['size'] = np.where(df['signal'] == 'short', -df['size'], df['size'])
            for order in df.groupby('order'):

                size = order[1]['size'].sum()/initial_size * total_size 
                for entry in order['entry'].groupby('entry'):

                    # Check if there is enough balance 
                    balance = getEquity()
                    size = size if size*entry[0] <= balance else balance/entry[0] # Hay un problema con esto y el cierre de operaciones según las operaciones independientes

                    # Prepare trade
                    trade = entry[1]['trade'].iloc[-1]
                    postOrder(product_id=symbol, side=side[0], order=order[0], 
                                entry=entry, sl_dist=trade.sldist, size=size)
                    
                    time.sleep(random.randint(40, 90))
    
    # Save portfolio to opened csv
    df = pd.DataFrame(portfolio.values())
    files.addOpenTrades(df, file=open_trades_name, mode='a')

    # Continued execution
    loop = False
    while loop:

        if start_time < dt.datetime.today().time() and dt.datetime.today().time() < end_time:

            data = getData(strategies, get_portfolio=False)
            trades = files.getOpenTrades(file=open_trades_name)
            # TODO! Check the exits for all the trades

            time.sleep(random.randint(60,120))

        # If market closed close execution
        elif end_time <= dt.datetime.today().time():
            loop = False

        # If market has not opened wait till it opens
        elif dt.datetime.today().time() < start_time:
            for s in strategies:
                for a in strategies[s].assets:
                    quote = dg.getQuote(product_id=tickers[a][broker])['data']
                    if quote['tradingStartTime'] < start_time:
                        start_time = quote['tradingStartTime']
                    if end_time < quote['tradingEndTime']:
                        end_time = quote['tradingEndTime']
                        
            time.sleep( time_interval(dt.datetime.today().time(), start_time, seconds=True) )

        else:
            time.sleep(random.randint(60,120))