package cn.gowin.control.data

/** Physical output identity; a preferred device is a request, never route proof. */
data class MusicOutput(val id: Int, val name: String, val a2dp: Boolean)

object MusicRoute {
    fun accepts(selectedId: Int?, actualId: Int?, availableIds: Set<Int>): Boolean =
        selectedId != null && selectedId in availableIds && selectedId == actualId
}
