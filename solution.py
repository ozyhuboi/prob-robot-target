from datetime import datetime

import numpy as np

import frame

blocked = []


class player(object):
    global blocked

    def __init__(self, board, quickRes=False, double=False, rule=2, maxIter=1000):
        # frame.board board: game board
        # bool quickRes: True: faster calculation; False: more precise result
        # TODO: Double checks
        # int double in [1 : 4]: cell types that need double check. False: no double check
        # int rule in [1 : 3]: search strategy.
        # int maxIter in [1 : inf]: max search times in a board

        self.b = board
        self.quickRes = quickRes
        self.double = double and not self.b.targetMoving
        self.rule = rule
        self.maxIter = maxIter

        # double check related
        self.doubleCount = np.zeros_like(self.b.cell, dtype=np.uint8)

        # report related
        self.reportHistory = []
        self.targetHistory = []
        self.searchHistory = []

        self.success = False
        self.history = []
        return

    # update functions
    # update b.prob after search
    def updateP(self, prob, row, col, quick=False, force=False, temp=False, blocked=[]):
        # bool force: True: force to normalize prob; False: depand on quick
        # bool temp: True: this is a temp prob, and will not update b.prob; False: update b.prob

        # process temp
        if temp:
            tempProb = np.copy(prob)
        else:
            tempProb = prob

        # update
        if (row, col) in blocked:
            tempProb[row, col] = 0
        else:
            tempProb[row, col] = tempProb[row, col] * self.b.failP[self.b.cell[row, col]]

        # process quick
        sumP = np.sum(tempProb)
        if not force and (self.quickRes or quick) and sumP > 0.5:
            if not temp:
                self.b.prob = tempProb
            return tempProb
        tempProb = self.normalizeP(tempProb, sumP)
        if not temp:
            self.b.prob = tempProb
        return tempProb

    # update b.prob after report
    def updateR(self, prob, report, quick=False, force=False, temp=False):
        solveFlag, targetMove = self.solveReport(report)
        if solveFlag:
            print('re-update')
            tempProb = self.reUpdateReport(temp=temp)
        else:
            tempProb = self.updateReport(prob, targetMove, quick=quick, force=force, temp=temp)
        return tempProb

    # report functions
    # analysis report history
    def solveReport(self, report):
        # returns:
        # bool solve Flag: True: reportHistory can translate to targetHistory; False: cannot translate
        # tuple targetMove with element (prev, post): target move from prev to post

        solveFlag = False
        if self.targetHistory:  # translatable
            targetMove = self.solveTarget(report)
        elif self.reportHistory:
            tPrevTer = self.reportHistory[-1] * report  # try to translate
            if 1 == np.count_nonzero(tPrevTer):  # translatable
                self.backtrackReport(tPrevTer)
                targetMove = self.solveTarget(report)
                solveFlag = True
            elif 2 == np.count_nonzero(tPrevTer):  # not translatable
                tReport = tuple(np.where(report > 0)[0])
                if len(tReport) == 1:
                    tReport = (tReport[0], tReport[0])
                targetMove = (tReport, tReport[:: -1])
            else:  # something wrong, target teleported
                print('E: solution.solveReport. wrong report')
                # print(report)
                exit()
        else:  # the first report
            tReport = tuple(np.where(report > 0)[0])
            if len(tReport) == 1:
                tReport = (tReport[0], tReport[0])
            targetMove = (tReport, tReport[:: -1])

        self.reportHistory.append(report)
        return (solveFlag, targetMove)

    # update temp report
    def updateReport(self, prob, targetMove, quick=False, force=False, temp=False):
        tempProb = np.zeros_like(prob, dtype=np.float16)
        # for each possible move
        for prev, post in targetMove:
            # for each possible prev block
            for row in range(self.b.rows):
                for col in range(self.b.cols):
                    if self.b.cell[row, col] == prev:
                        # update each possible post block
                        index = tuple(np.where(self.b.border[row, col, post, :])[0])
                        factor = len(index)
                        if factor:
                            nPos = ((row - 1, col), (row, col - 1), (row, col + 1), (row + 1, col))
                            tempP = prob[row, col] / factor
                            for i in index:
                                tempProb[nPos[i]] = tempProb[nPos[i]] + tempP

        sumP = np.sum(tempProb)

        if not force and (self.quickRes or quick) and sumP > 0.5:
            if not temp:
                self.b.prob = tempProb
            return tempProb
        tempProb = self.normalizeP(tempProb, sumP)
        if not temp:
            self.b.prob = tempProb
        return tempProb

    # re-update all report
    def reUpdateReport(self, temp=False):
        history = list(map(lambda x: np.where(x)[0][0], self.targetHistory))
        tempProb = np.full((self.b.rows, self.b.cols), (1. / (self.b.rows * self.b.cols)), dtype=np.float16)
        for i in range(len(history) - 1):
            tempProb = self.updateP(tempProb, *self.searchHistory[i], quick=True, temp=temp)
            tempProb = self.updateReport(self.b.prob, ((history[i], history[i + 1]),), quick=True, temp=temp)

        if not temp:
            self.b.prob = tempProb
        return tempProb

    # tool functions
    # resize prob so that sum == 1
    def normalizeP(self, tempProb, sumP=None):
        if sumP is None:
            sumP = np.sum(tempProb)
        if sumP == 0:
            print('E: solution.normalizeP. zero sumP')
            exit()
        tempProb = tempProb / sumP
        return tempProb

    def moveTo(self, row, col):
        while self.b.robot != (row, col):
            if self.b.robot[0] < row:
                self.b.move(self.b.robot[0] + 1, self.b.robot[1])
                self.history.append((self.b.robot, 'm'))
            elif self.b.robot[0] > row:
                self.b.move(self.b.robot[0] - 1, self.b.robot[1])
                self.history.append((self.b.robot, 'm'))
            if self.b.robot[1] < col:
                self.b.move(self.b.robot[0], self.b.robot[1] + 1)
                self.history.append((self.b.robot, 'm'))
            elif self.b.robot[1] > col:
                self.b.move(self.b.robot[0], self.b.robot[1] - 1)
                self.history.append((self.b.robot, 'm'))
        return

    def search(self, row, col):
        # move or teleport
        if self.b.moving:
            self.moveTo(row, col)

        # explore
        self.searchHistory.append((row, col))
        self.history.append(((row, col), 's'))
        return self.b.explore(row, col)

    # report tool functions
    # get temp target movement
    def solveTarget(self, report):
        diff = (report - self.targetHistory[-1]) > 0
        tTer = np.where(diff)
        tMove = (np.where(self.targetHistory[-1])[0][0], tTer[0][0])
        self.targetHistory.append(diff)
        return (tMove,)

    # translate reportHistory to targetHistory
    def backtrackReport(self, tPrevTer):
        tTer = tPrevTer > 0
        self.targetHistory.insert(0, tTer)
        reportList = self.reportHistory.copy()
        reportList.reverse()
        for report in reportList:
            tTer = (report - tTer) > 0
            self.targetHistory.insert(0, tTer)
        return

    # rule functions
    # get next block to search
    def getNext(self, row=None, col=None, rule=3):
        pos = None
        while pos in blocked or pos is None:
            if rule == 1:
                pos = self.maxProb(row, col)
            elif rule == 2:
                pos = self.maxSucP(row, col)
            elif rule == 3:
                pos = self.maxInfo(row, col)
            elif rule == 4:
                pos = self.minMove(row, col)
            elif rule == 5:
                pos = self.minCost(row, col)
            else:
                print('E: solution.getNext. wrong rule number.')
                exit()
        return pos

    # rule 1
    def maxProb(self, row=None, col=None):
        value = self.b.prob
        temp_val = np.zeros(shape=value.shape)
        neighbors = []
        print(row, col)
        print(len(value) - 1)
        for (i, j) in [(1, 0), (0, 1), (0, -1), (-1, 0)]:
            if 0 <= row + i < len(value):
                if 0 <= col + j < len(value):
                    if value[row + i, col + j] > 0:
                        print(row + i, col + j, value[row + i, col + j])
                        cell = (row + i, col + j)
                        neighbors.append(cell)
        print(neighbors)
        # print(temp_val.shape)
        # print(value.shape)
        for l in neighbors:
            temp_val[l] = value[l]
        # temp_val = np.where(temp_val)
        # eligible = np.argwhere(value==np.amax(value))
        # min = len(value) * 2
        # for e in eligible:
        #     d = manhattan(self, x=e, y=[row,col])
        #     if d < min:
        #         min = d
        #         min_pos = e
        # # pos = np.unravel_index(np.argmax(value), value.shape)
        pos = np.unravel_index(np.argmax(temp_val), temp_val.shape)
        # pos = (min_pos[0], min_pos[1])
        return pos

    # rule 2
    def maxSucP(self, row=None, col=None):
        value = self.b.prob * self.b.sucP
        # TODO: manhattan
        eligible = np.argwhere(value == np.amax(value))
        min = len(value) * 2
        for e in eligible:
            d = manhattan(self, x=e, y=[row, col])
            if d < min:
                min = d
                min_pos = e
        # pos = np.unravel_index(np.argmax(value), value.shape)
        pos = (min_pos[0], min_pos[1])
        return pos

    # rule 3
    def maxInfo(self, row=None, col=None):
        tempSucP = self.b.prob * self.b.sucP
        tempSucQ = 1 - tempSucP
        searchInfo = tempSucP * np.log2(tempSucP) + tempSucQ * np.log2(tempSucQ)  # there should be negative. use min to find max
        if self.b.targetMoving:
            pass  # TODO: value = searchreportInfo
        else:
            value = searchInfo
        pos = np.unravel_index(np.argmin(value), value.shape)  # use min instead
        return pos

    # rule 4 for moving = True, targetMoving = False
    def minMove(self, row=None, col=None):
        if row is None or col is None:
            row, col = self.b.robot
        find = self.b.prob * self.b.sucP
        value = find / np.exp2(self.b.dist[row, col])
        pos = np.unravel_index(np.argmax(value), value.shape)
        return pos

    # rule 5 for moving = True, targetMoving = True #WARN: DO NOT use in targetMoving = False, because factor will be truncated
    def minCost(self, row=None, col=None):
        if row is None or col is None:
            row, col = self.b.robot
        factor = np.empty_like(self.b.prob, dtype=np.float16)
        searchCost = np.empty_like(self.b.prob, dtype=np.float16)
        movingCost = np.zeros_like(self.b.prob, dtype=np.float16)

        base = np.sum(self.b.prob / self.b.sucP)

        valid = (self.b.prob != 0)
        if self.b.targetMoving:
            factor[valid] = 1 / (1 - self.b.prob[valid] * self.b.sucP[valid])
            searchCost[valid] = (factor[valid] - 1) * (base - self.b.prob[valid])

        else:
            factor = 1 / (1 - self.b.prob * self.b.sucP)
            searchCost = (factor - 1) * (base - self.b.prob)

        if self.b.moving:
            tempCost = np.sum(self.b.prob * self.b.dist[row, col])
            for nRow in range(self.b.rows):
                for nCol in range(self.b.cols):
                    if valid[nRow, nCol]:
                        movingCost[nRow, nCol] = (factor[nRow, nCol] - 1) * np.sum(self.b.prob * self.b.dist[nRow, nCol])

        value = searchCost - movingCost - self.b.dist[row, col]
        value[~valid] = -np.inf

        pos = np.unravel_index(np.argmax(value), value.shape)
        return pos

    # solver
    def solve(self):

        pos = None
        prev_pos = None

        prev_blocked = False
        while not self.success:
            if prev_blocked:
                pos = prev_pos
            else:
                pos = self.getNext(*self.b.robot, rule=self.rule)
            # print(pos)
            # print(self.b.sucP)
            if self.b.sucP[pos[0]][pos[1]] != 0:
                prev_pos = pos
                prev_blocked = False
            else:
                prev_blocked = True
                blocked.append(pos)
            # explore
            self.success, report = self.search(*pos)
            self.doubleCount[pos] = self.doubleCount[pos] + 1

            if self.success:
                break

            # double check
            if self.double and self.b.cell[pos] < self.double:
                self.updateP(self.b.prob, *pos)
                if self.b.targetMoving:
                    self.updateR(self.b.prob, report)
                self.b.probHistory.append(self.b.prob.copy())
                self.success, report = self.search(*pos)
                self.doubleCount[pos] = self.doubleCount[pos] + 1
                if self.success:
                    break

            # update
            self.updateP(self.b.prob, *pos, blocked=blocked)
            if self.b.targetMoving:
                self.updateR(self.b.prob, report)
            self.b.probHistory.append(self.b.prob.copy())

            # in case of too long loop
            if len(self.searchHistory) > self.maxIter:
                break

            # self.b.visualize()
        return


def manhattan(self, x, y):
    return abs(x[0] - y[0]) + abs(x[1] - y[1])


if __name__ == '__main__':
    print(datetime.now())
    # moving= True means agent can teleport
    b = frame.board(size=10, moving=False, targetMoving=False)
    p = player(b, double=False, rule=1)
    p.solve()
    print(datetime.now())
    for pp in b.probHistory:
        print(pp)
    print(p.history)
    print(len(p.history))

    # for i in range(500):
    #   tempB = copy.deepcopy(b)
    #   tempB.buildTerrain()
    #   tempB.hideTarget()
    #   p = player(tempB, double = 2, rule = 5)
    #   p.solve()
    #   # print(p.history)
    #   # print(len(p.targetHistory))
    #   print(len(p.history))

    # # p.b.visualize()
