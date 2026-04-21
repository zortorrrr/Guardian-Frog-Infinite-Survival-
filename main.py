import pygame

from game.game_manager import GameManager
from game.settings import WINDOW_HEIGHT, WINDOW_WIDTH


def main() -> None:
    pygame.init()
    pygame.display.set_caption("Guardian Frog - Prototype")
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))

    game = GameManager(screen)
    game.run()

    pygame.quit()


if __name__ == "__main__":
    main()