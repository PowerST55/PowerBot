"""
Piedra Papel Tijeras Master - Lógica de juego reutilizable
"""
from typing import Tuple


def validate_ppt_game(player1_points: float, player2_points: float, bet_amount: float) -> Tuple[bool, str]:
	"""
	Valida que ambos jugadores tengan puntos suficientes para jugar.
	
	Args:
		player1_points: Puntos del jugador 1
		player2_points: Puntos del jugador 2
		bet_amount: Cantidad apostada por cada jugador
		
	Returns:
		Tuple[es_valido, mensaje_error]
	"""
	if bet_amount <= 0:
		return False, "❌ La apuesta debe ser mayor a 0."
	
	if player1_points < bet_amount:
		return False, "❌ No tienes suficientes puntos para apostar."
	
	if player2_points < bet_amount:
		return False, f"❌ El rival no tiene suficientes puntos. Necesita mínimo {bet_amount:,.2f}."
	
	return True, ""


def determine_ppt_winner(player1_choice: str, player2_choice: str) -> Tuple[int, str]:
	"""
	Determina el ganador de Piedra Papel Tijeras.
	
	Args:
		player1_choice: Opción del jugador 1 (piedra, papel, tijeras)
		player2_choice: Opción del jugador 2 (piedra, papel, tijeras)
		
	Returns:
		Tuple[ganador, descripcion]:
			- ganador: 1 si gana player1, 2 si gana player2, 0 si es empate
			- descripcion: Descripción del resultado
	"""
	player1_choice = player1_choice.lower()
	player2_choice = player2_choice.lower()
	
	# Empate
	if player1_choice == player2_choice:
		return 0, f"¡Empate! Ambos eligieron {player1_choice}."
	
	# Piedra gana a Tijeras
	if player1_choice == "piedra" and player2_choice == "tijeras":
		return 1, "🪨 Piedra aplasta Tijeras."
	if player2_choice == "piedra" and player1_choice == "tijeras":
		return 2, "🪨 Piedra aplasta Tijeras."
	
	# Papel gana a Piedra
	if player1_choice == "papel" and player2_choice == "piedra":
		return 1, "📄 Papel cubre Piedra."
	if player2_choice == "papel" and player1_choice == "piedra":
		return 2, "📄 Papel cubre Piedra."
	
	# Tijeras gana a Papel
	if player1_choice == "tijeras" and player2_choice == "papel":
		return 1, "✂️ Tijeras cortan Papel."
	if player2_choice == "tijeras" and player1_choice == "papel":
		return 2, "✂️ Tijeras cortan Papel."
	
	return 0, "Opción inválida"


def get_ppt_emoji(choice: str) -> str:
	"""Retorna el emoji correspondiente a la opción."""
	choice = choice.lower()
	emojis = {
		"piedra": "🪨",
		"papel": "📄",
		"tijeras": "✂️"
	}
	return emojis.get(choice, "❓")
