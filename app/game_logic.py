from typing import Dict, List, Tuple, TypedDict

Coordinate = Tuple[int, int]
Matrix = List[List[int]]
from .functionWarGame import *

class BoardState(TypedDict):
    colors: Matrix
    shapes: Matrix
    numbers: Matrix
    warLocation: List[Coordinate]


def create_initial_state(rows: int, cols: int, game_number: int) -> BoardState:
    """TODO: replace with your own new-game initialization logic."""

    colors = [[0 for _ in range(cols)] for _ in range(rows)]
    for i in range(cols):
        for j in range(rows):
            if j <= 2:
                colors[i][j] = 1
            else:
                colors[i][j] = 2
    shapes = [[0 for _ in range(cols)] for _ in range(rows)]
    numbers = [[-1 for _ in range(cols)] for _ in range(rows)]
    shapes[1][1] = 1
    shapes[4][4] = 2
    numbers[1][1] = 6
    numbers[4][4] = 6
    warLocation = []

    return {
        "colors": colors,
        "shapes": shapes,
        "numbers": numbers,
        "warLocation": warLocation,
    }


def calculate_turn(
    player1_selected: List[Coordinate],
    player2_selected: List[Coordinate],
    turn_number: int,
    current_state: BoardState,
) -> BoardState:

    mapSize = [6, 6]
    baseAIndex = 7
    baseBIndex = 28
    soldierFromWarFieldA = 6
    soldierFromWarFieldB = 6

    complusaryEndTurn = 20

    posListA = transformPlayerSelectToPosList(player1_selected, mapSize)
    warField = transformShapesToWarField(current_state["shapes"])
    soldiers = transformNumbersToSoldiers(current_state["numbers"])
    posListB = transformPlayerSelectToPosList(player2_selected, mapSize)
    if len(posListA) == 0:
        posListA = [0]
    if len(posListB) == [0]:
        posListB = [35]

    indexListA, directionListA, defendLineBelongListA = generateDirectionA(posListA, warField, mapSize)
    soldiersMoveA, towardListA = linearProgramingA(mapSize, soldiers, indexListA, directionListA)
    soldierPolicyA = moveSoldiers(soldiersMoveA, towardListA, warField)
    indexListB, directionListB, defendLineBelongListB = generateDirectionB(posListB, warField, mapSize)
    soldiersMoveB, towardListB = linearProgramingB(mapSize, soldiers, indexListB, directionListB)
    soldierPolicyB = moveSoldiers(soldiersMoveB, towardListB, warField)

    soldiers, warField, warLocation, warLostA, warLostB, logisticsA, logisticsB = forwardNextStep(
        soldierPolicyA, soldierPolicyB, warField, mapSize,
        soldierFromWarFieldA, soldierFromWarFieldB, baseAIndex, baseBIndex)
    #
    # turn_number += 1
    #
    # if warField.count(1) == 0 or warField.count(2) == 0:
    #     for i in range(complusaryEndTurn - turn_number + 1):
    #         if warField.count(1) == 0:
    #             soldierPolicyA = [0 for _ in range(len(soldiers))]
    #             soldierPolicyB = soldiers
    #         else:
    #             soldierPolicyB = [0 for _ in range(len(soldiers))]
    #             soldierPolicyA = soldiers
    #         soldiers, warField, warLocation, warLostA, warLostB, logisticsA, logisticsB = forwardNextStep(
    #             soldierPolicyA, soldierPolicyB, warField, mapSize,
    #             soldierFromWarFieldA, soldierFromWarFieldB, baseAIndex, baseBIndex)
    #     turn_number = complusaryEndTurn

    newShapes = transformWarFieldToShapes(warField, mapSize)
    newNumbers = transformSoldiersToNumbers(soldiers, warField, mapSize)
    newWarLocation = transformWarLocationToCoordinate(warLocation, mapSize)

    """TODO: replace with your game-mechanics calculation."""
    newState = {
        "colors": current_state["colors"],
        "shapes": newShapes,
        "numbers": newNumbers,
        "warLocation": newWarLocation,
    }
    return newState


def get_flashing_cells(
    player1_selected: List[Coordinate],
    player2_selected: List[Coordinate],
    turn_number: int,
    state_after_turn: BoardState,
) -> List[Coordinate]:
    """TODO: return cells that should flash for one second after a turn."""
    return state_after_turn["warLocation"]
    # return []


def get_player_view(
    player_number: int,
    game_number: int,
    turn_number: int,
    shared_state: BoardState,
    boards: int = 3,
) -> BoardState:
    """Return a player-specific view of the board colors.

    boards=1: all blue
    boards=2: all red
    boards=3: left half blue, right half red
    boards=4: circle/player 1 sees boards=3; diamond/player 2 sees boards=2

    Shapes, numbers and war locations are shared game state; only the visible
    color treatment changes between board conditions.
    """
    rows = len(shared_state["colors"])
    cols = len(shared_state["colors"][0]) if rows else 0
    effective_boards = 3 if boards == 4 and player_number == 1 else (2 if boards == 4 else boards)

    if effective_boards == 1:
        colors = [[1 for _ in range(cols)] for _ in range(rows)]
    elif effective_boards == 2:
        colors = [[2 for _ in range(cols)] for _ in range(rows)]
    else:
        split = cols // 2
        colors = [[1 if c < split else 2 for c in range(cols)] for _ in range(rows)]

    return {
        "colors": colors,
        "shapes": shared_state["shapes"],
        "numbers": shared_state["numbers"],
        "warLocation": shared_state["warLocation"],
    }
